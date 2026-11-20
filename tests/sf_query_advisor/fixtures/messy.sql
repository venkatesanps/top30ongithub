CREATE OR REPLACE PROCEDURE p() RETURNS STRING LANGUAGE SQL AS $$ BEGIN SELECT 1; RETURN 'ok'; END; $$;
select a from t where name ilike '%smith%';
select x from t where id = :1 and y = ?;
SELEC broken from;
select * from big_events where event_date::date = '2026-01-01' limit 10;
