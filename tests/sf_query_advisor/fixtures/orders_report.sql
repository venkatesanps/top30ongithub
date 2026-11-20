-- Daily revenue by region (a typical BI query)
WITH recent AS (
  SELECT * FROM analytics.sales.orders
  WHERE TO_DATE(order_ts) = '2026-03-15'
)
SELECT c.region, COUNT(DISTINCT r.customer_id) AS buyers, SUM(r.amount) AS revenue
FROM recent r
JOIN analytics.sales.customers c ON r.customer_id = c.customer_id
WHERE c.status NOT IN (SELECT status FROM analytics.ref.blocked_status)
GROUP BY c.region
ORDER BY revenue DESC;
