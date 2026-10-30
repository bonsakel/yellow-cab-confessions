select reason_code, count(*) as example_count
from {{ ref("mart_blooper_examples") }}
group by reason_code
having count(*) > {{ var("blooper_examples_per_rule") }}
