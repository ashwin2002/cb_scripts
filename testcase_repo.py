import calendar
from datetime import datetime

years_to_check = [2016, 2017, 2018, 2019]
month_str = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

from couchbase.cluster import Cluster
from couchbase.cluster import PasswordAuthenticator
from couchbase.bucket import Bucket as CouchbaseBucket

cluster = Cluster("http://127.0.0.1", bucket_class=CouchbaseBucket)
cluster.authenticate(PasswordAuthenticator("Administrator", 'password'))
cb = cluster.open_bucket("testcase_repo")

end_date = datetime.strptime("{0}-{1}-{2}".format(2015, 12, 31), "%Y-%m-%d")
total = 0
for row in cb.n1ql_query("SELECT * FROM `testcase_repo`"):
    is_created = False
    for changeHist in row["testcase_repo"]["changeHistory"]:
        commitDate = changeHist["commitDate"].split(" ")[0]
        commitDate = datetime.strptime(commitDate, "%Y-%m-%d")

        if commitDate > end_date:
            break
                
        if changeHist["changeType"] == "create":
            is_created = True
        elif changeHist["changeType"] == "delete":
            is_created = False
    if is_created:
        total += 1

print("Total cases as of 2015: {0}".format(total))

for year in years_to_check:
    if year == 2019:
        months = [1]
    else:
        months = range(1, 13)

    for month in months:
        create = delete = 0
        is_created = is_deleted = False

        start_date, end_date = 1, calendar.monthrange(year, month)[1]
        start_date = datetime.strptime("{0}-{1}-{2}".format(year, month, start_date), "%Y-%m-%d")
        end_date = datetime.strptime("{0}-{1}-{2}".format(year, month, end_date), "%Y-%m-%d")

        for row in cb.n1ql_query("SELECT * FROM `testcase_repo`"):
            is_created = is_deleted = False
            for changeHist in row["testcase_repo"]["changeHistory"]:
                commitDate = changeHist["commitDate"].split(" ")[0]
                commitDate = datetime.strptime(commitDate, "%Y-%m-%d")

                if commitDate < start_date:
                    continue
                elif commitDate > end_date:
                    break
                
                if changeHist["changeType"] == "create":
                    is_deleted = False
                    is_created = True
                elif changeHist["changeType"] == "delete":
                    is_created = False
                    is_deleted = True
            if is_created:
                create += 1
            elif is_deleted:
                delete += 1
        total += create - delete
        print("{0} {1} - Created: {2}, Deleted: {3}, Total: {4}".format(month_str[month-1], year, create, delete, total))
