import os
import sys
import csv
import utils

def get_test_info(info_csv,save_file):
    can = 0
    can_list = []
    can_dict = {}

    cros = 0
    cros_list = []
    cros_dict = {}
    with open(info_csv, mode ='r')as file:
        csvFile = csv.reader(file)
        for line in csvFile:
            if "#project" in line:
                continue
            project_name = line[0].split("/")[-1]
            sha = line[1]
            module = line[2]
            victim = line[3]
            polluter = line[4]
            tag = victim
            if victim.split(".")[0:-1] == polluter.split(".")[0:-1]:
                can += 1
                test_info = [project_name,sha,module,victim,polluter]
                can_list.append(test_info)
                if tag not in can_dict:
                    can_dict[tag] = test_info
                # print(project_name,sha,module,victim,polluter)
            else:
                cros += 1
                test_info = [project_name,sha,module,victim,polluter]
                cros_list.append(test_info)
                if tag not in cros_dict:
                    cros_dict[tag] = test_info
                # print(line)
                # exit(0)

    # write same class
    with open(save_file, 'w') as csvfile: 
        csvwriter = csv.writer(csvfile) 
        for info in can_list:
            csvwriter.writerows([info])

    # write cros class     
    with open(save_file, 'a') as csvfile: 
        csvwriter = csv.writer(csvfile) 
        for info in cros_list:
            csvwriter.writerows([info])

    print(len(can_dict))
    print(len(cros_dict))
    print(len(can_list))
    print(len(cros_list))
    final_dict = {}
    final_dict.update(can_dict)
    final_dict.update(cros_dict)
    print(len(final_dict))
    return final_dict

def match_idoft(can_dict,prdata,save2_file):
    can_test = []
    cros_test = []
    pr_data_list = []
    with open(prdata, mode ='r')as file:
        csvFile = csv.reader(file)
        for line in csvFile:
            if "Project URL" in line or "project_url" in line:
                continue
            pr_data_list.append(line)

    for tag1 in can_dict:
        test_info = can_dict[tag1]
        fd = False
        for line in pr_data_list:
            project = line[0]
            project_name = project.split("/")[-1]
            sha = line[1]
            module = line[2]
            test = line[3]
            type = line[4]
            status = line[5]
            pr = line[6]
            notes = line[7]
            tag = test
            if tag1 == tag:
                # print(test_info)
                # exit(0)
                if test_info[3] == test: #and test_info[2] == module: #test_info[1] == sha and #victim
                    test_list = []
                    test_list.extend([project,test_info[1],test_info[2],test_info[3],type,status,pr,notes])
                    test_list.append(test_info[4])#polluter
                    can_test.append(test_list)
                    fd = True
                    # print(test_list)
                else:
                    print(tag1)
                    # print(test_info[1],sha,test_info[3],test,test_info[2],module)
                    exit(0)
        if fd == False:
            print(tag1)
    
    print(len(can_test))

    with open(save2_file, 'w') as csvfile: 
        csvwriter = csv.writer(csvfile) 
        for info in can_test:
            # print(info)
            csvwriter.writerows([info])

def get_file_path(input_csv,withpath_csv,clone_dir):
    all = []
    with open(input_csv, mode ='r')as file:
        csvFile = csv.reader(file)
        for line in csvFile:
            if "Project URL" in line or "project_url" in line:
                continue
            project = line[0]
            name = project.split("/")[-1]
            sha = line[1]
            victim = line[3]
            polluter = line[8]
            victim_method = victim.split(".")[-1]
            polluter_method = polluter.split(".")[-1]
            victim_class_name = victim.split(".")[-2]
            polluter_class_name = polluter.split(".")[-2]
            victim_file = ""
            polluter_file = ""
            info = []
            victim_path_fd = False  
            polluter_path_fd = False 
            victim_test_path = "/".join(victim.split(".")[:-1])
            polluter_test_path = "/".join(polluter.split(".")[:-1])

            project_dir = os.path.join(clone_dir,sha,name)
            for root, dirs, files in os.walk(project_dir):
                for file in files:
                    file_path = os.path.join(root,file)
                    if victim_path_fd == False:
                        if file_path.endswith(".java") and file == victim_class_name+".java" \
                            and "/test/" in file_path and victim_test_path in file_path:
                                data = utils.read_java(file_path)
                                if victim_method in data:
                                    victim_file = file_path
                                    victim_path_fd = True
                                    if victim_class_name == polluter_class_name and polluter_path_fd == False:
                                        polluter_file = file_path
                                        polluter_path_fd = True
                    if polluter_path_fd == False:
                        if file_path.endswith(".java") and file == polluter_class_name+".java" \
                            and "/test/" in file_path and polluter_test_path in file_path:
                                data = utils.read_java(file_path)
                                if polluter_method in data:
                                    polluter_file = file_path
                                    polluter_path_fd = True
            if False in [polluter_path_fd, victim_path_fd]:
                print(line,polluter_path_fd,victim_path_fd)
                continue

            info.extend(line)
            info.append(polluter_file)
            info.append(victim_file)
            all.append(info)
    print(len(all))
    with open(withpath_csv, 'w') as csvfile: 
        csvwriter = csv.writer(csvfile) 
        for info in all:
            # print(info)
            csvwriter.writerows([info])

if __name__ == "__main__":
    # args = sys.argv[1:]
    info_csv = "/home/azureuser/ODRepair/experiments/data/results.csv"
    save_file = "ods.csv"
    save2_file = "odss.csv"
    can_dict = get_test_info(info_csv,save_file)
    pr_data = "idoft/pr-data.csv"
    match_idoft(can_dict,pr_data,save2_file)
    withpath_csv = "odsss.csv"
    clone_dir = "projects"
    get_file_path(save2_file,withpath_csv,clone_dir)