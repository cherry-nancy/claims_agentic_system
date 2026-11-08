import duckdb

from snf_pa.paths import raw_table, sql_path

Q = f"""
select count(*) as medicare,
       sum(case when discharge_location = 'SKILLED NURSING FACILITY' then 1 else 0 end) as snf
from read_csv_auto('{sql_path(raw_table("mimiciv-3.1/hosp/admissions"))}')
where insurance = 'Medicare'
"""
print(duckdb.sql(Q).fetchall())
