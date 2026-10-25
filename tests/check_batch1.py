import duckdb

Q = """
select count(*) as medicare,
       sum(case when discharge_location = 'SKILLED NURSING FACILITY' then 1 else 0 end) as snf
from read_csv_auto('data/mimiciv-3.1/hosp/admissions.csv.gz')
where insurance = 'Medicare'
"""
print(duckdb.sql(Q).fetchall())
