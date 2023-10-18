import os
import sys
import csv

def read_log(log_file,save_file):
    fields = [ "project", "sha", "module", 
                    "test_full_name","type","fix time","is_good_fix","failure_type"]
    with open(save_file, 'w', newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fields)
        writer.writeheader()
        
        file = open(log_file, 'r')
        lines = file.readlines()
        num = 0
        for line in lines:
            line_info = line.strip()
            if line_info.startswith("[****GOOD FIX*****]"):
                num += 1
                print(line_info)
                lst = line_info.split(" ")
                time = lst[3]
                test = lst[6]
                type = lst[9]
                project = lst[12]
                sha = lst[14]
                module = lst[16]
                is_good_fix = "True"
                final_res = {"project": project, "sha": sha, "module": module, "test_full_name": test, \
                            "type":type, "fix time":time,"is_good_fix": is_good_fix,"failure_type": "None"}
                writer.writerow(final_res)
                print("Done", num)
            if line_info.startswith("[****BAD FIXES ***"):
                num += 1
                print(line_info)
                lst = line_info.split(" ")
                time = "None"
                test = lst[5]
                type = lst[8]
                project = lst[11]
                sha = lst[13]
                module = lst[15]
                if "compilation_error" in lst[2]:
                    failure_type = "compilation_error"
                elif "test_fail" in lst[2]:
                    failure_type = "test_fail"
                is_good_fix = "False"
                final_res = {"project": project, "sha": sha, "module": module, "test_full_name": test, \
                            "type":type, "fix time":time,"is_good_fix": is_good_fix,"failure_type":failure_type}
                writer.writerow(final_res)
                print("Done", num)


if __name__ == "__main__":
    args = sys.argv[1:]
    log_file = args[0]
    save_file = args[1]
    read_log(log_file,save_file)