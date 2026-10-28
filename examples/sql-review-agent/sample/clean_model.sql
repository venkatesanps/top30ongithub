-- A clean example: should produce no findings
insert into refined.account_totals (account_id, total_amount, as_of)
select p.account_id, sum(p.amount) as total_amount, current_date() as as_of
from raw.positions p
join raw.accounts a on a.account_id = p.account_id
where p.load_ts >= dateadd(day, -1, current_date())
  and not exists (select 1 from raw.closed_accounts c where c.account_id = p.account_id)
group by p.account_id;
