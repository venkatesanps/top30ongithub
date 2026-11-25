# Snowflake DE architecture

The three layers, ingestion, storage, transformation, caches, protection, governance and sharing; Gen1 credit figures. Checked November 2026.

1. Snowflake's three layers: _____, _____ and storage.
   - Snowflake's three layers: **cloud services**, **compute (warehouses)** and storage.
   - _tags: layers; source: README.md, 1_
2. **Which layer holds the result cache and the query optimizer?**
   - Cloud services
   - _tags: layers, cache; source: README.md, 1_
3. **When are cloud-services credits actually billed?**
   - Only the part above 10% of that day's warehouse credits
   - _tags: layers, cost; source: README.md, 1_
4. **How is a warehouse billed when it resumes?**
   - Per second, with a 60-second minimum each time it starts
   - _tags: compute, cost; source: README.md, 1_
5. **Gen1 credits per hour for X-Small, Small, Medium, Large, X-Large?**
   - 1, 2, 4, 8, 16: each size doubles
   - _tags: compute, cost; source: README.md, 1_
6. **Gen2 X-Small credits per hour on AWS?**
   - 1.35 (Azure: 1.25)
   - _tags: compute, cost, gen2; source: README.md, 1_
7. **How do you keep a new warehouse on Gen1 where Gen2 is the default?**
   - Create it with RESOURCE_CONSTRAINT = STANDARD_GEN_1
   - _tags: compute, gen2; source: README.md, 1_
8. **Which column of SHOW WAREHOUSES tells Gen1 from Gen2?**
   - resource_constraint
   - _tags: compute, gen2; source: README.md, 1_
9. **A Medium finishes in 1 minute; an X-Small takes 4. Which costs more?**
   - Neither: 4 credits/h × 1 min equals 1 credit/h × 4 min
   - _tags: compute, cost; source: README.md, 1_
10. **Many users queue on one warehouse. Scale up or out?**
   - Out: a multi-cluster warehouse (Enterprise)
   - _tags: compute, performance; source: README.md, 2_
11. **How long does Snowflake keep load metadata that stops COPY INTO reloading a file?**
   - 64 days
   - _tags: ingestion; source: README.md, 2_
12. **What does FORCE = TRUE on COPY INTO risk?**
   - Loading files again, so duplicate rows
   - _tags: ingestion; source: README.md, 2_
13. **What does CREATE OR REPLACE TABLE do to COPY load metadata?**
   - Wipes it, so the next COPY reloads every file still in the stage
   - _tags: ingestion; source: README.md, 2_
14. **How is Snowpipe billed since December 2025?**
   - 0.0037 credits per GB ingested, no per-file charge
   - _tags: ingestion, cost; source: README.md, 2_
15. **Snowpipe bills a gzipped CSV at which size?**
   - Its uncompressed size
   - _tags: ingestion, cost; source: README.md, 2_
16. Snowpipe auto-ingest on AWS: S3 event → _____ → Snowpipe.
   - Snowpipe auto-ingest on AWS: S3 event → **SQS** → Snowpipe.
   - _tags: ingestion; source: README.md, 2_
17. **Which object holds IAM trust to a bucket so nobody puts keys in a stage?**
   - A storage integration
   - _tags: ingestion, security; source: README.md, 2_
18. **Which table type stores data as Apache Iceberg in your own bucket?**
   - Iceberg tables
   - _tags: ingestion, storage; source: README.md, 2_
19. **Micro-partition size, and measured how?**
   - 50–500 MB, before compression
   - _tags: storage; source: README.md, 3_
20. **Why does an UPDATE create Time Travel history?**
   - Micro-partitions are immutable, so new ones are written
   - _tags: storage, protection; source: README.md, 3_
21. **What lets Snowflake skip micro-partitions during a query?**
   - Pruning on per-column min/max metadata
   - _tags: storage, performance; source: README.md, 3_
22. **Does SELECT from a stream advance its offset?**
   - No; only DML that consumes the stream does
   - _tags: transformation; source: README.md, 4_
23. **How does a task skip runs when there's no new data?**
   - WHEN SYSTEM$STREAM_HAS_DATA('<stream>')
   - _tags: transformation, cost; source: README.md, 4_
24. **What does TARGET_LAG = '10 minutes' mean?**
   - Data at most ~10 minutes stale (a target), not a refresh every 10 minutes
   - _tags: transformation; source: README.md, 4_
25. **What TARGET_LAG should intermediate dynamic tables use?**
   - DOWNSTREAM
   - _tags: transformation; source: README.md, 4_
26. **Result cache lifetime?**
   - 24 hours, renewed on reuse up to 31 days from the first run
   - _tags: cache; source: README.md, 5_
27. **Name two things that stop result cache reuse.**
   - Changed underlying data; a different query text or a function like CURRENT_TIMESTAMP()
   - _tags: cache; source: README.md, 5_
28. **What happens to the warehouse cache on suspend?**
   - It is dropped
   - _tags: cache, compute; source: README.md, 5_
29. **Which session parameter turns result reuse off for benchmarking?**
   - USE_CACHED_RESULT = FALSE
   - _tags: cache; source: README.md, 5_
30. **Which feature speeds point lookups on high-cardinality columns?**
   - Search optimization (Enterprise)
   - _tags: performance; source: README.md, 5_
31. **Can a materialized view join two tables?**
   - No, one base table only (Enterprise)
   - _tags: performance; source: README.md, 5_
32. **What caps Query Acceleration Service spend?**
   - QUERY_ACCELERATION_MAX_SCALE_FACTOR
   - _tags: performance, cost; source: README.md, 5_
33. **Maximum Time Travel on Standard Edition?**
   - 1 day
   - _tags: protection, editions; source: README.md, 6_
34. **Maximum Time Travel on Enterprise for permanent tables?**
   - 90 days
   - _tags: protection, editions; source: README.md, 6_
35. **Fail-safe period, and for which tables?**
   - 7 days, permanent tables only
   - _tags: protection; source: README.md, 6_
36. **Who can recover data from Fail-safe?**
   - Only Snowflake Support
   - _tags: protection; source: README.md, 6_
37. **Why make ETL work tables transient?**
   - No Fail-safe storage for data you can rebuild
   - _tags: protection, cost; source: README.md, 6_
38. **Restore a table to just before a bad DELETE.**
   - CLONE ... BEFORE(STATEMENT => '<query id>'), then swap
   - _tags: protection; source: README.md, 6_
39. **Does cloning a single table copy its grants?**
   - No, unless you add COPY GRANTS
   - _tags: protection, security; source: README.md, 6_
40. **Which pipes are skipped when a database is cloned?**
   - Pipes that read from internal stages
   - _tags: protection; source: README.md, 6_
41. **Who pays for compute used in a reader account?**
   - The provider
   - _tags: sharing, cost; source: README.md, 8_
42. **In a direct share, who pays for the queries?**
   - The consumer, on its own warehouses
   - _tags: sharing, cost; source: README.md, 8_
43. **Why share secure views rather than plain views?**
   - Consumers can't see a secure view's definition
   - _tags: sharing, security; source: README.md, 8_
44. **Name four Enterprise-only governance policies.**
   - Masking, row access, aggregation, projection
   - _tags: security, editions; source: README.md, 7_
45. **Which system role should create everyday objects?**
   - SYSADMIN (or custom roles granted to it)
   - _tags: security; source: README.md, 7_
