{{ config(materialized="table") }}

with payment_codes as (
    select distinct
        payment_type,
        rate_code_id
    from {{ ref("stg_yellow_trips") }}
)
select
    md5(concat_ws(
        '|',
        coalesce(cast(payment_type as varchar), '<NULL>'),
        coalesce(cast(rate_code_id as varchar), '<NULL>')
    )) as payment_key,
    payment_type,
    case payment_type
        when 0 then 'Flex fare'
        when 1 then 'Credit card'
        when 2 then 'Cash'
        when 3 then 'No charge'
        when 4 then 'Dispute'
        when 5 then 'Unknown'
        when 6 then 'Voided trip'
        else 'Unmapped payment type'
    end as payment_type_label,
    rate_code_id,
    case rate_code_id
        when 1 then 'Standard rate'
        when 2 then 'JFK flat fare'
        when 3 then 'Newark'
        when 4 then 'Nassau or Westchester'
        when 5 then 'Negotiated fare'
        when 6 then 'Group ride'
        else 'Unmapped rate code'
    end as rate_code_label
from payment_codes
