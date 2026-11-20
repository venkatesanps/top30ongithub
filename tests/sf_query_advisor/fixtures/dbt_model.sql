{{ config(materialized='incremental', unique_key='id') }}

with src as (
    select * from {{ source('shop', 'events') }}
    {% if is_incremental() %}
    where event_ts > (select max(event_ts) from {{ this }})
    {% else %}
    where event_ts > '2020-01-01'
    {% endif %}
),

final as (
    select id, user_id, event_ts::date as event_date, {{ dbt_utils.generate_surrogate_key(['id']) }} as sk
    from src
)

select * from final
