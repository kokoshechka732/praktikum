import os

import duckdb

BASE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(BASE, "data")
OUT = os.path.join(BASE, "out")
con = duckdb.connect()

con.execute(f"""CREATE VIEW us AS SELECT * FROM read_csv_auto('{OUT}/log_users.csv')""")
con.execute(f"""CREATE VIEW users AS SELECT * FROM read_csv('{D}/users.csv', delim=';', header=false,
    quote='"', escape='"', null_padding=true, ignore_errors=true,
    names=['id','name','email','password','is_verified','created_at','updated_at','deleted_at',
           'logout_at','trial_used_at','remna_id','remna_short_id','referrer_user_id','referal_balance',
           'role','referral_config_id','dashamail_id','segment_id','ga4_client_id','is_was_guest',
           'beta_tester','appmetrica_device_id','appmetrica_profile_id'],
    types={{'id':'BIGINT'}})""")
con.execute(f"""CREATE VIEW sub AS SELECT * FROM read_csv('{D}/subscribe.csv', delim=';', header=false,
    quote='"', escape='"', null_padding=true, ignore_errors=true,
    names=['id','user_id','product_id','expired_time','created_at','order_id','disabled_at',
           'next_product_id','pre_payment','pre_payment_notification','next_period_id'],
    types={{'id':'BIGINT','user_id':'BIGINT','product_id':'BIGINT'}})""")

print("пользователей с логами:", con.sql("SELECT count(*) FROM us").fetchall())
print("\nесть ли они в таблице users:")
print(con.sql("""
    SELECT count(*) AS matched,
           sum(CASE WHEN u.trial_used_at IS NOT NULL THEN 1 ELSE 0 END) AS trial,
           sum(CASE WHEN u.deleted_at IS NOT NULL THEN 1 ELSE 0 END) AS deleted
    FROM us l JOIN users u ON u.id = l.user_id::BIGINT
""").fetchall())
print("\nплатящие среди них:")
print(con.sql("""
    SELECT count(DISTINCT l.user_id) AS with_logs_and_sub
    FROM us l JOIN sub s ON s.user_id = l.user_id::BIGINT
""").fetchall())
print("\nсредние ошибки у платящих и неплатящих:")
print(con.sql("""
    WITH paid AS (SELECT DISTINCT user_id FROM sub)
    SELECT CASE WHEN l.user_id::BIGINT IN (SELECT user_id FROM paid) THEN 'платит' ELSE 'не платит' END AS grp,
           count(*) AS users, round(avg(l.errors),0) AS avg_err, median(l.errors) AS med_err
    FROM us l GROUP BY grp
""").fetchall())
print("\nошибки у пользователей с триалом и без (только matched):")
print(con.sql("""
    SELECT CASE WHEN u.trial_used_at IS NOT NULL THEN 'триал был' ELSE 'триала не было' END AS grp,
           count(*) AS users, round(avg(l.errors),0) AS avg_err, median(l.errors) AS med_err
    FROM us l JOIN users u ON u.id = l.user_id::BIGINT GROUP BY grp
""").fetchall())
print("\nдоля всех пользователей базы с триалом и подпиской:")
print(con.sql("""
    SELECT (SELECT count(*) FROM users) AS all_users,
           (SELECT count(*) FROM users WHERE trial_used_at IS NOT NULL) AS trial_users,
           (SELECT count(DISTINCT user_id) FROM sub) AS paid_users
""").fetchall())
print("\nошибки на пользователя по ОС (только matched):")
print(con.sql("""
    SELECT l.os, count(*) users, round(avg(l.errors),0) avg_err
    FROM us l JOIN users u ON u.id = l.user_id::BIGINT GROUP BY l.os ORDER BY avg_err DESC
""").fetchall())
