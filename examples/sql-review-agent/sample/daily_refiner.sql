-- Daily refiner: positions joined to accounts (sample with deliberate problems)
create or replace table refined.daily_positions as
select *
from raw.positions p, raw.accounts a
where to_date(p.load_ts) = current_date()
  and p.account_id not in (select account_id from raw.closed_accounts);

with ranked as (
  select account_id, amount, row_number() over (partition by account_id order by load_ts desc) rn
  from raw.positions
  order by account_id
)
select account_id, amount from ranked where rn = 1
union
select account_id, amount from raw.manual_adjustments;

delete from refined.daily_positions;
