-- Snowflake data engineering lab: one pass through the architecture, end to end.
-- Companion to README.md in this folder. Run it statement by statement in a Snowsight worksheet,
-- in a TRIAL or SANDBOX account. Don't run it in a work account without approval.
--
-- Cost: one X-Small Gen1 warehouse (1 credit/hour) that suspends after 60 seconds idle.
-- A full run should use well under 1 credit. Nothing is left scheduled: the task is run by
-- hand and never resumed, and the dynamic table is suspended after its first refresh.
-- Step 12 drops everything this lab creates.
--
-- Status: written from Snowflake's docs (November 2026); it hasn't been run end to end on a live
-- account yet. If a result disagrees with its "-- expect:" line, trust Snowflake and fix the line.
--
-- Every object is named LAB_*. "-- expect:" says what you should see. Steps marked
-- [Enterprise] need Enterprise Edition or higher; skip them on Standard.

---------------------------------------------------------------------------------------------
-- 0. Compute: a small Gen1 warehouse that stops itself
---------------------------------------------------------------------------------------------
USE ROLE SYSADMIN;
USE SECONDARY ROLES NONE;
-- New users default to ALL secondary roles, so a trial user's ACCOUNTADMIN would stay active
-- behind SYSADMIN and the step 9 policies would show everything. Restored in step 12.

CREATE WAREHOUSE IF NOT EXISTS LAB_WH
  WAREHOUSE_SIZE = XSMALL
  RESOURCE_CONSTRAINT = STANDARD_GEN_1   -- new warehouses may default to Gen2 (1.35x credits on AWS)
  AUTO_SUSPEND = 60
  AUTO_RESUME = TRUE
  INITIALLY_SUSPENDED = TRUE;

SHOW WAREHOUSES LIKE 'LAB_WH';
-- expect: size X-Small, auto_suspend 60, resource_constraint STANDARD_GEN_1

USE WAREHOUSE LAB_WH;

---------------------------------------------------------------------------------------------
-- 1. Storage hierarchy: account > database > schema > objects
---------------------------------------------------------------------------------------------
CREATE DATABASE IF NOT EXISTS LAB_DE;
CREATE SCHEMA IF NOT EXISTS LAB_DE.RAW;
CREATE SCHEMA IF NOT EXISTS LAB_DE.CORE;
USE SCHEMA LAB_DE.RAW;

---------------------------------------------------------------------------------------------
-- 2. A source system, simulated: 100,000 synthetic orders (no files or credentials needed)
---------------------------------------------------------------------------------------------
CREATE OR REPLACE TRANSIENT TABLE LAB_DE.RAW.LAB_ORDERS_SRC AS
SELECT
  ROW_NUMBER() OVER (ORDER BY SEQ4())                               AS order_id,  -- SEQ4() alone can have gaps
  'cust' || UNIFORM(1, 5000, RANDOM())                              AS customer_id,
  'user' || UNIFORM(1, 5000, RANDOM()) || '@example.com'            AS email,
  DECODE(UNIFORM(1, 4, RANDOM()), 1, 'NA', 2, 'EMEA', 3, 'APAC', 'LATAM') AS region,
  ROUND(UNIFORM(5, 500, RANDOM()) + UNIFORM(0, 99, RANDOM()) / 100, 2) AS amount,
  DATEADD(minute, -UNIFORM(0, 60 * 24 * 90, RANDOM()), CURRENT_TIMESTAMP())::TIMESTAMP_NTZ AS ordered_at
FROM TABLE(GENERATOR(ROWCOUNT => 100000));
-- Transient: rebuildable data, so no Fail-safe storage to pay for.

SELECT COUNT(*), MIN(ordered_at), MAX(ordered_at) FROM LAB_DE.RAW.LAB_ORDERS_SRC;
-- expect: 100000 rows across the last 90 days. Check the Query Profile: COUNT(*) alone is
-- answered from metadata.

---------------------------------------------------------------------------------------------
-- 3. Stage and file format: unload to files, the way an upstream system would drop them
---------------------------------------------------------------------------------------------
CREATE OR REPLACE FILE FORMAT LAB_DE.RAW.LAB_CSV
  TYPE = CSV
  FIELD_OPTIONALLY_ENCLOSED_BY = '"'
  SKIP_HEADER = 1
  NULL_IF = ('', 'NULL')
  COMPRESSION = GZIP;

CREATE OR REPLACE STAGE LAB_DE.RAW.LAB_STAGE
  FILE_FORMAT = LAB_DE.RAW.LAB_CSV
  DIRECTORY = (ENABLE = TRUE);

COPY INTO @LAB_DE.RAW.LAB_STAGE/orders/
  FROM LAB_DE.RAW.LAB_ORDERS_SRC
  FILE_FORMAT = (FORMAT_NAME = LAB_DE.RAW.LAB_CSV)
  HEADER = TRUE
  MAX_FILE_SIZE = 5000000;
-- COPY INTO <location> unloads. expect: a few .csv.gz files

LIST @LAB_DE.RAW.LAB_STAGE/orders/;
ALTER STAGE LAB_DE.RAW.LAB_STAGE REFRESH;
SELECT relative_path, size FROM DIRECTORY(@LAB_DE.RAW.LAB_STAGE);
-- The directory table lists the stage's files as rows.

---------------------------------------------------------------------------------------------
-- 4. Load with COPY INTO <table>: validate first, load, then load again
---------------------------------------------------------------------------------------------
CREATE OR REPLACE TABLE LAB_DE.RAW.LAB_ORDERS (
  order_id     NUMBER,
  customer_id  VARCHAR,
  email        VARCHAR,
  region       VARCHAR,
  amount       NUMBER(10, 2),
  ordered_at   TIMESTAMP_NTZ
);

COPY INTO LAB_DE.RAW.LAB_ORDERS
  FROM @LAB_DE.RAW.LAB_STAGE/orders/
  VALIDATION_MODE = RETURN_ERRORS;
-- expect: no rows (no errors). Nothing is loaded in validation mode.

COPY INTO LAB_DE.RAW.LAB_ORDERS
  FROM @LAB_DE.RAW.LAB_STAGE/orders/
  ON_ERROR = ABORT_STATEMENT;
-- expect: one row per file with status LOADED; 100000 rows in total

COPY INTO LAB_DE.RAW.LAB_ORDERS
  FROM @LAB_DE.RAW.LAB_STAGE/orders/;
-- expect: "Copy executed with 0 files processed." The table's 64-day load metadata skips files
-- it already loaded. This is what makes re-running a failed load safe.

SELECT file_name, row_count, status
FROM TABLE(INFORMATION_SCHEMA.COPY_HISTORY(TABLE_NAME => 'LAB_ORDERS',
                                           START_TIME => DATEADD(hour, -1, CURRENT_TIMESTAMP())));

---------------------------------------------------------------------------------------------
-- 5. CDC with a stream, applied by a task (run by hand, never scheduled)
---------------------------------------------------------------------------------------------
CREATE OR REPLACE TABLE LAB_DE.CORE.LAB_ORDERS_CLEAN LIKE LAB_DE.RAW.LAB_ORDERS;
INSERT INTO LAB_DE.CORE.LAB_ORDERS_CLEAN SELECT * FROM LAB_DE.RAW.LAB_ORDERS;

CREATE OR REPLACE STREAM LAB_DE.RAW.LAB_ORDERS_STREAM ON TABLE LAB_DE.RAW.LAB_ORDERS;

INSERT INTO LAB_DE.RAW.LAB_ORDERS
SELECT order_id + 1000000, customer_id, email, region, amount, CURRENT_TIMESTAMP()::TIMESTAMP_NTZ
FROM LAB_DE.RAW.LAB_ORDERS_SRC SAMPLE (10 ROWS);
UPDATE LAB_DE.RAW.LAB_ORDERS SET amount = amount + 1 WHERE order_id <= 5;

SELECT METADATA$ACTION, METADATA$ISUPDATE, COUNT(*)
FROM LAB_DE.RAW.LAB_ORDERS_STREAM GROUP BY 1, 2;
-- expect: INSERT/FALSE 10, plus INSERT/TRUE 5 and DELETE/TRUE 5 for the updated rows.
-- Reading the stream with SELECT doesn't advance it; only DML that consumes it does.

CREATE OR REPLACE TASK LAB_DE.CORE.LAB_APPLY_ORDERS
  WAREHOUSE = LAB_WH
  SCHEDULE = '60 MINUTE'
  WHEN SYSTEM$STREAM_HAS_DATA('LAB_DE.RAW.LAB_ORDERS_STREAM')
AS
  MERGE INTO LAB_DE.CORE.LAB_ORDERS_CLEAN t
  USING (SELECT * FROM LAB_DE.RAW.LAB_ORDERS_STREAM WHERE METADATA$ACTION = 'INSERT') s
    ON t.order_id = s.order_id
  WHEN MATCHED THEN UPDATE SET t.amount = s.amount
  WHEN NOT MATCHED THEN INSERT (order_id, customer_id, email, region, amount, ordered_at)
    VALUES (s.order_id, s.customer_id, s.email, s.region, s.amount, s.ordered_at);
-- Created suspended. Don't resume it: that would start the hourly schedule.

-- Running a task needs the EXECUTE TASK account privilege, which by default only ACCOUNTADMIN
-- has. On a trial account, grant it once (uncomment these three lines):
-- USE ROLE ACCOUNTADMIN;
-- GRANT EXECUTE TASK ON ACCOUNT TO ROLE SYSADMIN;
-- USE ROLE SYSADMIN;
-- At work, ask your admin, or run the MERGE from the task body directly instead.
EXECUTE TASK LAB_DE.CORE.LAB_APPLY_ORDERS;

SELECT name, state, error_message
FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY(TASK_NAME => 'LAB_APPLY_ORDERS'))
ORDER BY scheduled_time DESC LIMIT 1;
-- expect: SUCCEEDED (wait a few seconds and re-run if it shows SCHEDULED or EXECUTING)

SELECT COUNT(*) FROM LAB_DE.RAW.LAB_ORDERS_STREAM;
-- expect: 0. The MERGE consumed the stream, so its offset moved forward.
SELECT COUNT(*) FROM LAB_DE.CORE.LAB_ORDERS_CLEAN;
-- expect: 100010

---------------------------------------------------------------------------------------------
-- 6. Declarative pipeline: a dynamic table
---------------------------------------------------------------------------------------------
CREATE OR REPLACE DYNAMIC TABLE LAB_DE.CORE.LAB_DAILY_REVENUE
  TARGET_LAG = '1 day'
  WAREHOUSE = LAB_WH
  REFRESH_MODE = INCREMENTAL
AS
  SELECT region, DATE_TRUNC(day, ordered_at) AS order_day, COUNT(*) AS orders, SUM(amount) AS revenue
  FROM LAB_DE.CORE.LAB_ORDERS_CLEAN
  GROUP BY 1, 2;

SHOW DYNAMIC TABLES LIKE 'LAB_DAILY_REVENUE' IN SCHEMA LAB_DE.CORE;
-- expect: refresh_mode INCREMENTAL, target_lag 1 day. TARGET_LAG is a staleness target, not a schedule.

SELECT * FROM LAB_DE.CORE.LAB_DAILY_REVENUE ORDER BY order_day DESC, region LIMIT 8;

ALTER DYNAMIC TABLE LAB_DE.CORE.LAB_DAILY_REVENUE SUSPEND;
-- Suspended so it can't refresh again after the lab.

---------------------------------------------------------------------------------------------
-- 7. Caches: result cache versus running on the warehouse
---------------------------------------------------------------------------------------------
SELECT region, SUM(amount) FROM LAB_DE.CORE.LAB_ORDERS_CLEAN GROUP BY region ORDER BY region;
SELECT region, SUM(amount) FROM LAB_DE.CORE.LAB_ORDERS_CLEAN GROUP BY region ORDER BY region;
-- expect: the second run's Query Profile shows QUERY RESULT REUSE (no warehouse time)

ALTER SESSION SET USE_CACHED_RESULT = FALSE;
SELECT region, SUM(amount) FROM LAB_DE.CORE.LAB_ORDERS_CLEAN GROUP BY region ORDER BY region;
-- expect: runs on the warehouse. In the profile, "Percentage scanned from cache" is above 0%
-- (warehouse cache) if the warehouse didn't suspend in between.
ALTER SESSION UNSET USE_CACHED_RESULT;

---------------------------------------------------------------------------------------------
-- 8. Time Travel, zero-copy clone, UNDROP
---------------------------------------------------------------------------------------------
DELETE FROM LAB_DE.CORE.LAB_ORDERS_CLEAN;   -- the classic mistake: no WHERE clause
SET bad_delete = LAST_QUERY_ID();

SELECT COUNT(*) FROM LAB_DE.CORE.LAB_ORDERS_CLEAN;                                   -- expect: 0
SELECT COUNT(*) FROM LAB_DE.CORE.LAB_ORDERS_CLEAN BEFORE(STATEMENT => $bad_delete);  -- expect: 100010

CREATE OR REPLACE TABLE LAB_DE.CORE.LAB_ORDERS_RESTORED
  CLONE LAB_DE.CORE.LAB_ORDERS_CLEAN BEFORE(STATEMENT => $bad_delete);
ALTER TABLE LAB_DE.CORE.LAB_ORDERS_CLEAN SWAP WITH LAB_DE.CORE.LAB_ORDERS_RESTORED;
SELECT COUNT(*) FROM LAB_DE.CORE.LAB_ORDERS_CLEAN;                                   -- expect: 100010
-- The clone shares micro-partitions with the history, so it's instant and adds no storage
-- until one side changes.

DROP TABLE LAB_DE.CORE.LAB_ORDERS_RESTORED;
UNDROP TABLE LAB_DE.CORE.LAB_ORDERS_RESTORED;
SHOW TABLES HISTORY LIKE 'LAB_ORDERS_RESTORED' IN SCHEMA LAB_DE.CORE;
-- expect: back, with dropped_on empty

SHOW TABLES LIKE 'LAB_ORDERS%' IN DATABASE LAB_DE;
-- Compare the retention_time and kind columns: LAB_ORDERS_SRC is TRANSIENT (no Fail-safe).

---------------------------------------------------------------------------------------------
-- 9. [Enterprise] Governance: column masking and row access
---------------------------------------------------------------------------------------------
-- If applying a policy fails on privileges, your account uses centralized policy management:
-- run this step with a role that has APPLY MASKING POLICY / APPLY ROW ACCESS POLICY.
CREATE OR REPLACE MASKING POLICY LAB_DE.CORE.LAB_MASK_EMAIL AS (val STRING) RETURNS STRING ->
  CASE WHEN IS_ROLE_IN_SESSION('ACCOUNTADMIN') THEN val
       ELSE REGEXP_REPLACE(val, '^[^@]+', '*****') END;

ALTER TABLE LAB_DE.CORE.LAB_ORDERS_CLEAN MODIFY COLUMN email SET MASKING POLICY LAB_DE.CORE.LAB_MASK_EMAIL;
SELECT email FROM LAB_DE.CORE.LAB_ORDERS_CLEAN LIMIT 3;
-- expect (as SYSADMIN): *****@example.com

CREATE OR REPLACE TABLE LAB_DE.CORE.LAB_REGION_ACCESS (role_name STRING, region STRING);
INSERT INTO LAB_DE.CORE.LAB_REGION_ACCESS VALUES ('SYSADMIN', 'EMEA');

CREATE OR REPLACE ROW ACCESS POLICY LAB_DE.CORE.LAB_RAP_REGION AS (r STRING) RETURNS BOOLEAN ->
  IS_ROLE_IN_SESSION('ACCOUNTADMIN')
  OR EXISTS (SELECT 1 FROM LAB_DE.CORE.LAB_REGION_ACCESS a
             WHERE a.role_name = CURRENT_ROLE() AND a.region = r);

ALTER TABLE LAB_DE.CORE.LAB_ORDERS_CLEAN ADD ROW ACCESS POLICY LAB_DE.CORE.LAB_RAP_REGION ON (region);
SELECT region, COUNT(*) FROM LAB_DE.CORE.LAB_ORDERS_CLEAN GROUP BY region;
-- expect (as SYSADMIN): only EMEA

ALTER TABLE LAB_DE.CORE.LAB_ORDERS_CLEAN DROP ROW ACCESS POLICY LAB_DE.CORE.LAB_RAP_REGION;
ALTER TABLE LAB_DE.CORE.LAB_ORDERS_CLEAN MODIFY COLUMN email UNSET MASKING POLICY;

---------------------------------------------------------------------------------------------
-- 10. Sharing: a secure view (the share itself needs ACCOUNTADMIN, so it stays commented out)
---------------------------------------------------------------------------------------------
CREATE OR REPLACE SECURE VIEW LAB_DE.CORE.LAB_REVENUE_SHARED AS
  SELECT region, order_day, revenue FROM LAB_DE.CORE.LAB_DAILY_REVENUE;
-- Share secure views only: a consumer can't see a secure view's definition.
--
-- USE ROLE ACCOUNTADMIN;
-- CREATE SHARE LAB_SHARE;
-- GRANT USAGE ON DATABASE LAB_DE TO SHARE LAB_SHARE;
-- GRANT USAGE ON SCHEMA LAB_DE.CORE TO SHARE LAB_SHARE;
-- GRANT SELECT ON VIEW LAB_DE.CORE.LAB_REVENUE_SHARED TO SHARE LAB_SHARE;
-- ALTER SHARE LAB_SHARE ADD ACCOUNTS = <consumer_account>;   -- the consumer pays its own compute
-- DROP SHARE LAB_SHARE;

---------------------------------------------------------------------------------------------
-- 11. What did this cost?
---------------------------------------------------------------------------------------------
-- Returns rows only for ACCOUNTADMIN or a role with the MONITOR USAGE privilege. Without either,
-- it comes back empty: look under Admin > Cost management in Snowsight instead.
SELECT warehouse_name, SUM(credits_used) AS credits
FROM TABLE(INFORMATION_SCHEMA.WAREHOUSE_METERING_HISTORY(
       DATE_RANGE_START => DATEADD(hour, -4, CURRENT_TIMESTAMP()), WAREHOUSE_NAME => 'LAB_WH'))
GROUP BY 1;
-- expect: well under 1 credit. Metering can lag by a few hours, so check again tomorrow.

---------------------------------------------------------------------------------------------
-- 12. Clean up: drop everything the lab created
---------------------------------------------------------------------------------------------
USE SECONDARY ROLES ALL;
DROP DATABASE IF EXISTS LAB_DE;
DROP WAREHOUSE IF EXISTS LAB_WH;
SHOW DATABASES LIKE 'LAB_DE';
-- expect: no rows. The dropped database stays in Time Travel for 1 day (UNDROP DATABASE LAB_DE).
