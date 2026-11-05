-- Daily positions load (sample Oracle SQL, invented for tests)
CREATE TABLE stg_positions (
  position_id   NUMBER(18),
  account_no    VARCHAR2(30 BYTE),
  market_value  NUMBER,
  as_of_date    DATE
) PARTITION BY RANGE (as_of_date) (PARTITION p0 VALUES LESS THAN (DATE '2020-01-01'));

SELECT /*+ parallel(p 8) */ p.account_no, NVL(p.market_value, 0) mv,
       DECODE(a.status, 'A', 'Active', 'Closed') status
  FROM stg_positions p, accounts a
 WHERE p.account_no = a.account_no(+)
   AND p.as_of_date = TRUNC(SYSDATE) - 1
   AND ROWNUM <= 100;

SELECT emp_id, LEVEL, mgr_id FROM org START WITH mgr_id IS NULL CONNECT BY PRIOR emp_id = mgr_id ORDER SIBLINGS BY emp_id;

INSERT INTO audit_log (id, note) SELECT audit_seq.NEXTVAL, 'loaded' FROM dual;

SELECT account_no FROM accounts WHERE nickname = '' ;

SELECT account_no FROM accounts@legacy_db MINUS SELECT account_no FROM stg_positions;
