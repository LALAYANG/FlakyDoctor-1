

import csv
import sys
import os
import javalang
import git
import get_uniq_projects
import openai
import datetime
import glob
import utils
import tiktoken
import subprocess
from subprocess import Popen, PIPE
import re
import extract_fixes
import update_pom
import process_line
import sample_tests
from pathlib import Path

run_nondex_cmds = "/home/azureuser/flaky/cmds/run_nondex.sh"
checkout_project_cmds = "/home/azureuser/flaky/cmds/checkout_project.sh"

def gpt_fix_err_OD(test,err_msg,last_patch,failure_code,updated_helper_res,err_methods):
    for key in updated_helper_res:
        print(updated_helper_res[key])

    test_type = test["type"].split(";")[0]
    test["gpt_full_response"] = ""
    test["patch"] = ""
    test["patch_file"] = ""
    related_testclass_code = ""
    victim_name = test["victim"].split(".")[-1]
    polluter_name = test["polluter"].split(".")[-1]
    class_helper_list = []
    for pv in updated_helper_res:
        for key in updated_helper_res[pv]["global_vars"]:
            class_helper_list.append(updated_helper_res[pv]["global_vars"][key])

    for pv in updated_helper_res:
        for key in updated_helper_res[pv]:
            if key == "global_vars" or key == "method_names":
                continue
            elif updated_helper_res[pv][key] != None:
                for m in updated_helper_res[pv][key]:
                    class_helper_list.append(updated_helper_res[pv][key][m])

    related_testclass_code = "\n".join(class_helper_list) + "\n"

    #test_content
    #test_method,related_testclass_code,err_msg,located_err_lines,method_with_err
    failure_code_str = ""
    if failure_code != None:
        failure_code_str = ("\t".join(failure_code)).strip()

    prompt = "To fix the original flaky test {}, the following code is from your previous answer {}, I received errors: {}\n The error is caused by {} in method {}.\n\
    Fix the errors, fix the flaky test, keep the code in the same format:\
    You should think about the solution step by step, print all code between //<fix start> and //<fix end>, do not omit any code. Do not print any other text in the response.\n \
    Flaky tests non-deterministically pass or fail due to dependencies of test orders. A polluter pollutes the shared status with victim, which makes the victim fail. \n \
    When two tests are dependent on each other through a shared state, This shared state can be a variable used by two tests, a file that both tests write or read from, or any resource that is shared between two tests. \n \
    Flakiness can be resolved by removing the dependency between tests. \n \
    You should follow the rules below for fixing the code:\n \
    - Do not add code out of methods. Do not print methods that you don't change anything of them.\n \
    - Print complete code of the method you changed. Don't omit unchanged code of that method.\n \
    - Do not expect me to modify or replace anything in the code.\n \
    - Print all text which is out of code starting with \"//\". \n \
    - Do not add or delete methods.\n \
    - Do not change sugnatures and modifiers of all methods. \n \
    - Fix the flakiness by modifying the provided code. You may make changes to all methods in the class. But do not add code out of methods.\n \
    - Print all code between //<fix start> and //<fix end>.\n \
    - Update dependencies in pom.xml if needed, put the code between <!-- <pom.xml start> --> and <!-- <pom.xml end> -->.  Provide a specific version for the dependency you add. Do not add existing dependencies. Do not include my artifact in your pom.xml code.\n \
    - Your code should be compilable without any errors.\n \
    - Make sure all the arguments are correct.\n \
    - Use compatible types for all variables.\n \
    - Do not define or write helper methods out of the test, make sure all methods you want to call are inside the test method.\n \
    - Update import list if needed, put the code between //<import start> and //<import end>. \n \
    - Assume required classes for original code are setup correctly and do not include them in your code. \n \
        ".format(victim_name,related_testclass_code,err_msg,failure_code_str,"\t".join(err_methods))
    
    print(prompt)

    response = openai.ChatCompletion.create(
        model = "gpt-4", #"gpt-3.5-turbo",
        temperature = 0.2,
        messages = [
            {"role": "user", 
            "content":prompt}
        ]
    )
    test["gpt_full_response"] = response["choices"][0]["message"]["content"]
    return test,response,prompt

#helper_res from parse_helper_methods
#locate_err(surefire_output,test["polluter_file"],test["victim_file"],polluter_format_test,victim_format_test,helper_res)
def locate_err(surefire_output,polluter_file,victim_file,polluter_format_test,victim_format_test,helper_res):
    res = {
        "victim": {"failure_code":[],
                    "failure_lines":[],
                    "helper_res":{},
                    "method_names":[]
                    },
        "polluter": {"failure_code":[],
                    "failure_lines":[],
                    "helper_res":{},
                    "method_names":[]
                    }
    }
    if victim_file == polluter_file:
        failure_code,failure_lines,helper_res,method_names = locate_err_victim(surefire_output,polluter_file,victim_file,polluter_format_test,victim_format_test,helper_res)
        res["victim"]["failure_code"] = failure_code.copy()
        res["victim"]["failure_lines"] = failure_lines.copy()
        res["victim"]["helper_res"] = helper_res.copy()
        res["victim"]["method_names"] = method_names.copy()
        return res
        # return failure_code,failure_lines,helper_res,method_names
    else:
        victim_failure_code,victim_failure_lines,victim_helper_res,victim_helper_method_names = locate_err_victim(surefire_output,polluter_file,victim_file,polluter_format_test,victim_format_test,helper_res)
        # return failure_code,failure_lines,helper_res,method_names
        polluter_failure_code,polluter_failure_lines,polluter_helper_res,polluter_helper_method_names = locate_err_polluter(surefire_output,polluter_file,victim_file,polluter_format_test,victim_format_test,helper_res)
        res["victim"]["failure_code"] = victim_failure_code.copy()
        res["victim"]["failure_lines"] = victim_failure_lines.copy()
        res["victim"]["helper_res"] = victim_helper_res.copy()
        res["victim"]["method_names"] = victim_helper_method_names.copy()
        res["polluter"]["failure_code"] = polluter_failure_code.copy()
        res["polluter"]["failure_lines"] = polluter_failure_lines.copy()
        res["polluter"]["helper_res"] = polluter_helper_res.copy()
        res["polluter"]["method_names"] = polluter_helper_method_names.copy()

        print(res["victim"]["helper_res"])
        print(res["polluter"]["helper_res"])
        # exit(0)
        return res

def locate_err_victim(surefire_output,polluter_file,victim_file,polluter_format_test,victim_format_test,helper_res):
    if victim_file != polluter_file:
        print("victim_file != polluter_file")
        # exit(0)
    # get failures in victim class
    failure_code,failure_lines,method_names = process_line.nod_get_line_location_msg(surefire_output,victim_file,victim_format_test)
    victim_class_content = utils.read_java(victim_file)
    res_code = {}
    for method_name in method_names:
        res = utils.get_err_method(method_name,victim_class_content,failure_lines)
        if res != None:
            method_code = res[3]
            method_name = res[2]
            if method_name not in res_code:
                res_code[method_name]=method_code
        #[start,end,method_name,method_code,node.annotations]
    for res_snip in res_code:
        exist = False
        for pv in helper_res:
            for key in helper_res[pv]:
                if key == "global_vars" or key == "method_names":
                    continue
                else:
                    for sub_key in helper_res[pv][key]:
                        if res_code[res_snip] == helper_res[pv][key][sub_key]:
                            exist = True
                            break
        if exist == False:
            helper_res[victim]["err_method"][res_snip] = res_code[res_snip]
    
    # print(failure_code,failure_lines,method_names,res_code)
    # print(helper_res)

    return failure_code,failure_lines,helper_res,method_names

def locate_err_polluter(surefire_output,polluter_file,victim_file,polluter_format_test,victim_format_test,helper_res):
    if victim_file != polluter_file:
        print("victim_file != polluter_file")
        # exit(0)
    # get failures in victim class
    failure_code,failure_lines,method_names = process_line.nod_get_line_location_msg(surefire_output,polluter_file,polluter_format_test)
    polluter_class_content = utils.read_java(polluter_file)
    res_code = {}
    for method_name in method_names:
        res = utils.get_err_method(method_name,polluter_class_content,failure_lines)
        if res != None:
            method_code = res[3]
            method_name = res[2]
            if method_name not in res_code:
                res_code[method_name]=method_code
        #[start,end,method_name,method_code,node.annotations]
    for res_snip in res_code:
        exist = False
        for pv in helper_res:
            for key in helper_res[pv]:
                if key == "global_vars" or key == "method_names":
                    continue
                else:
                    for sub_key in helper_res[pv][key]:
                        if res_code[res_snip] == helper_res[pv][key][sub_key]:
                            exist = True
                            break
        if exist == False:
            helper_res[victim]["err_method"][res_snip] = res_code[res_snip]
    
    # print(failure_code,failure_lines,method_names,res_code)
    # print(helper_res)

    return failure_code,failure_lines,helper_res,method_names


#res = {"victim":{"victim_test":{},"before":{}, "after":{}, "global_vars":{}, "err_method":{},"method_names":[]},
#    "polluter":{"polluter_test":{},"before":{}, "after":{}, "global_vars":{}, "err_method":{},"method_names":[]}}

def parse_helper_methods(test):
    res = {"victim":{"victim_test":{},"before":{}, "after":{}, "global_vars":{}, "err_method":{},"method_names":[]},
            "polluter":{"polluter_test":{},"before":{}, "after":{}, "global_vars":{}, "err_method":{},"method_names":[]}}
    
    victim_file_path = test["victim_file"]
    file = open(victim_file_path, 'r', errors='ignore')
    victim_test_class = file.read()
    victim_method_name = test["victim"].split(".")[-1]
    victim_test = utils.get_test_method(victim_method_name,victim_test_class)
    res["victim"]["victim_test"][victim_method_name] = victim_test[3]
    victim_before_after_line = utils.get_helper_methods(victim_test_class)
    victim_global_vars = utils.get_global_vars(victim_test_class,victim_before_after_line["earlist_line"])
    if victim_before_after_line["before"] != None:
        res["victim"]["before"] = victim_before_after_line["before"]
    if victim_before_after_line["after"] != None:
        res["victim"]["after"] = victim_before_after_line["after"]
    if victim_before_after_line["earlist_line"] != None:
        res["victim"]["global_vars"] = victim_global_vars
    res["victim"]["method_names"] = victim_before_after_line["method_names"]

    polluter_file_path = test["polluter_file"]
    file = open(polluter_file_path, 'r', errors='ignore')
    polluter_test_class = file.read()
    polluter_method_name = test["polluter"].split(".")[-1]
    polluter_test = utils.get_test_method(polluter_method_name,polluter_test_class)
    res["polluter"]["polluter_test"][polluter_method_name] = polluter_test[3]
    if victim_file_path == polluter_file_path:
        return res
    else:
        print("polluter and victim not from same file")
        polluter_before_after_line = utils.get_helper_methods(polluter_test_class)
        polluter_global_vars = utils.get_global_vars(polluter_test_class,polluter_before_after_line["earlist_line"])
        if polluter_before_after_line["before"] != None:
            res["polluter"]["before"] = polluter_before_after_line["before"]
        if polluter_before_after_line["after"] != None:
            res["polluter"]["after"] = polluter_before_after_line["after"]
        if polluter_before_after_line["earlist_line"] != None:
            res["polluter"]["global_vars"] = polluter_global_vars
        res["polluter"]["method_names"] = polluter_before_after_line["method_names"]
        return res

def gpt_fix_OD(test,err_msg,failure_code,updated_helper_res,err_methods):
    for key in updated_helper_res:
        print(updated_helper_res[key])
    
    test_type = test["type"].split(";")[0]
    test["gpt_full_response"] = ""
    test["patch"] = ""
    test["patch_file"] = ""
    related_testclass_code = ""
    victim_name = test["victim"].split(".")[-1]
    polluter_name = test["polluter"].split(".")[-1]
    class_helper_list = []
    for pv in updated_helper_res:
        for key in updated_helper_res[pv]["global_vars"]:
            class_helper_list.append(updated_helper_res[pv]["global_vars"][key])

    for pv in updated_helper_res:
        for key in updated_helper_res[pv]:
            if key == "global_vars" or key == "method_names":
                continue
            elif updated_helper_res[pv][key] != None:
                for m in updated_helper_res[pv][key]:
                    class_helper_list.append(updated_helper_res[pv][key][m])

    related_testclass_code = "\n".join(class_helper_list) + "\n"

    #    Flaky tests non-deterministically pass or fail due to dependencies of test orders. A polluter pollutes the shared status with victim, which makes the victim fail.\n \

    prompt = "You are a software testing expert. I'm going to ask you to fix a flaky test.\n \
    Flaky tests non-deterministically pass or fail due to dependencies of test orders. A polluter pollutes the shared status with victim, which makes the victim fail. \n \
    When two tests are dependent on each other through a shared state, This shared state can be a variable used by two tests, a file that both tests write or read from, or any resource that is shared between two tests. \n \
    Flakiness can be resolved by removing the dependency between tests. \n \
    You should think about the solution step by step, print all code between //<fix start> and //<fix end>, do not omit any code. Do not print any other text in the response.\n \
    Problem definition: {} is the victim flaky test you need to fix, {} is the polluter, they are located in the following code of a java class:\n {}\n \
    When the test fails, I get the following error:\n {}\n The error is caused by {} in method {}.\n\
    You should follow the rules below for fixing the code:\n \
    - Do not add code out of methods. Do not print methods that you don't change anything of them.\n \
    - Print complete code of the method you changed. Don't omit unchanged code of that method.\n \
    - Do not expect me to modify or replace anything in the code.\n \
    - Print all text which is out of code starting with \"//\". \n \
    - Do not add or delete methods.\n \
    - Do not change sugnatures and modifiers of all methods. \n \
    - Fix the flakiness by modifying the provided code. You may make changes to all methods in the class. But do not add code out of methods. \n \
    - Print all code between //<fix start> and //<fix end>.\n \
    - Update dependencies in pom.xml if needed, put the code between <!-- <pom.xml start> --> and <!-- <pom.xml end> -->.  Provide a specific version for the dependency you add. Do not add existing dependencies. Do not include my artifact in your pom.xml code.\n \
    - Your code should be compilable without any errors.\n \
    - Make sure all the arguments are correct.\n \
    - Use compatible types for all variables.\n \
    - Do not define or write helper methods out of the test, make sure all methods you want to call are inside the test method.\n \
    - Update import list if needed, put the code between //<import start> and //<import end>. \n \
    - Assume required classes for original code are setup correctly and do not include them in your code. \n \
        ".format(victim_name,polluter_name,related_testclass_code,err_msg,("\t".join(failure_code)).strip(),"\t".join(err_methods))
    
    print(prompt)

    response = openai.ChatCompletion.create(
        model = "gpt-4", #"gpt-3.5-turbo",
        temperature = 0.2,
        messages = [
            {"role": "user", 
            "content":prompt}
        ]
    )
    test["gpt_full_response"] = response["choices"][0]["message"]["content"]
    print(prompt)
    print(response)
    # exit(0)
    return test,response,prompt

# def output_nondex(test_type,project,sha,format_test,module,cloneDir,tag,times,file_path):
#     output = extract_fixes.verify_by_tool(test_type,project,sha,format_test,module,cloneDir,tag,times)
#     msg, res, failure_code = process_nondex_output(output,file_path,format_test)
#     return "\n".join(msg), res, failure_code,output

# msg, res, original_failure_code,surefire_output
# output_surefire(test["type"],test["project_name"],test["sha"],test["module"],polluter_format_test,victim_format_test,cloneDir,"BeforeFix","1",test["victim_file"])

def output_surefire(test_type,project,sha,module,polluter_format_test,victim_format_test,cloneDir,tag,times,polluter_file,victim_file):
    output = extract_fixes.verify_by_surefire(test_type,project,sha,module,polluter_format_test,victim_format_test,cloneDir,tag,times)
    msg, res, failure_code = process_surefire_output(output,polluter_file,victim_file,polluter_format_test,victim_format_test)
    return "\n".join(msg), res, failure_code,output
    # print(output)

def process_surefire_output(output,polluter_file,victim_file,polluter_format_test,victim_format_test):
    res = ""
    msg = []
    seq_list = output.split("\n")
    if "COMPILATION ERROR" in output:
        res = "COMPILATION ERROR"
        for line in seq_list:
            if "To see the full stack trace of the errors" in line:
                break
            if "ERROR" in line and "Help 1" not in line:
                simp_line = line.replace(victim_file,"").replace("\x1b[1;31m","").replace("\x1b[m","").replace("\x1b[1m","").replace("\x1b[36m","").replace("\n", "\t").replace("[ERROR]","").strip()
                if "cannot find symbol" in simp_line:
                    tmp_seq = simp_line.split(" ")[0]
                    if "[" in tmp_seq and "]" in tmp_seq and "," in tmp_seq:
                        simp_line = "cannot find symbol"
                        if simp_line not in msg:
                            msg.append(simp_line)
                if simp_line not in msg:
                    msg.append(simp_line)
        
        return msg,res,None
    else:
        if "test failures" not in output:
            if "BUILD FAILURE" in output:
                return msg,"BUILD FAILURE",None
            
        for pre_line in seq_list:
            line = pre_line.replace("\x1b[1;31m","").replace("\x1b[m","").replace("\x1b[1m","").replace("\x1b[36m","").strip()
            if "cannot find symbol" in line:
                tmp_seq = line.split(" ")[0]
                if "[" in tmp_seq and "]" in tmp_seq and "," in tmp_seq:
                    line = "cannot find symbol"
                    msg.append(line)
            if "There are test failures" in line:
                res = "test failures"
                # msg.append(line)
            if "Failed tests:" in line:
                msg.append(line)
                res = "test failures"
            if "Tests in error:" in line:
                indx = seq_list.index(pre_line)
                msg.append(seq_list[indx+1])
                res = "test failures"

        s_list = output.split("<<< FAILURE!")[1:]
        for item in s_list:
            if "Results" in item:
                if "Failures: 1" in item or "Failures: 2" in item:
                    add_info = item.split("Results")[0]
                    res = "test failures"
                    if "at" in add_info:
                        err_info = add_info.split("\tat")[0]
                        if err_info not in msg:
                            msg.append(err_info.replace("\n","\t"))
            #Errors: 1
            if "Results" in item:
                if "Errors: 1" in item or "Errors: 2" in item:
                    add_info = item.split("Results")[0]
                    res = "test failures"
                    if "at" in add_info:
                        err_info = add_info.split("\tat")[0]
                        if err_info not in msg:
                            msg.append(err_info.replace("\n","\t"))
        if len(msg) == 0:
            for pre_line in seq_list:
                line = pre_line.replace("\x1b[1;31m","").replace("\x1b[m","").replace("\x1b[1m","").replace("\x1b[36m","")
                if "ERROR" in line and "Help 1" not in line and "Time elapsed:" not in line \
                    and "For more information about the errors and possible solutions" not in line:
                    line.replace(victim_file,"")
                    msg.append(line)
        failure_code,failure_lines = process_line.get_line_location_msg(output,victim_file,victim_format_test)
        if len(msg) > 0:
            uniq_msg = []
            victim_testname = victim_format_test.replace("#",".")
            victim_classname = victim_testname.split("#")[0]
            for m in msg:
                new_m = m.replace(victim_testname,"").replace(victim_classname,"").replace("[ERROR]","").replace("ERROR!","").replace("ERROR!","")
                update_m = new_m
                if "Time elapsed:" in new_m:
                    timesec = (new_m.split("Time elapsed:")[1]).split("sec")[0]
                    update_m = new_m.replace(timesec,"").replace("Time elapsed:","").replace(" sec ","")
                if update_m.strip() not in uniq_msg:
                    uniq_msg.append(update_m.strip())
            return uniq_msg,res,failure_code
        else:
            if "ERROR" in output:
                return msg,"BUILD FAILURE",None
            else:
                return msg,"test pass",None

def simply_parse(gpt_full_response):
    simple_patch = {"code":"", "import":[], "pom":""}
    code = gpt_full_response["choices"][0]["message"]["content"]
    import_pattern = re.compile(r'^\s*import\s+([\w.]+);', re.MULTILINE)
    imp_matches = import_pattern.findall(code)
    for match in imp_matches:
        imp = "import " + match + ";"
        if imp not in simple_patch["import"]:
            simple_patch["import"].append(imp)
    potential_match_final = ""
    if "<!-- <pom.xml start> -->" in code and "<!-- <pom.xml end> -->" in code:
        pom_stat = (code.split("<!-- <pom.xml start> -->")[1]).split("<!-- <pom.xml end> -->")[0]
        simple_patch["pom"] = pom_stat
    if "//<fix start>" in code:
        potential_match = code.split("//<fix start>")[1]
        potential_match_final = potential_match
        if "//<fix end>" in code:
            potential_match_final = " \n " + potential_match.split("//<fix end>")[0] + " \n "
    if potential_match_final != "":
        import_pattern = re.compile(r'^\s*import\s+([\w.]+);', re.MULTILINE)
        p_imp_matches = import_pattern.findall(code)
        for match in p_imp_matches:
            tmp = "import " + match + ";"
            if tmp in potential_match_final:
                pfinal = potential_match_final.replace(tmp,"")
                potential_match_final = pfinal
    simple_patch["code"] = potential_match_final
    return simple_patch


def apply_before_processing(project,sha,module,test_fullname,test_type,method_name,simple_patch,file_path,cloneDir,tag,times):
    final_class = apply_patch(project,sha,module,test_fullname,test_type,method_name,simple_patch,file_path,cloneDir)
    print(("[Simple patch start] Running test with simple patch {} with type {} from project {} sha {} module {} \
                    ").format(test_fullname, test_type, project, sha, module),flush = True)
    if final_class != None:
        format_test = extract_fixes.replace_last(test_fullname, '.', '#')
        msg, res, failure_code,ndx_output = output_nondex(test_type,project,sha,format_test,module,cloneDir,tag,times,file_path)
    else:
        print("error when applying simple patch without processing")
    print(("[Simple patch end] Running test with simple patch {} with type {} from project {} sha {} module {}, simple result: {} \
                    ").format(test_fullname, test_type, project, sha, module,res),flush = True)
    extract_fixes.git_stash(project, sha, cloneDir,file_path)
    return res


# patch = parse_patch(test["gpt_full_response"],test["victim_file"],test["polluter_file"],test["victim"],test["polluter"],time)
def parse_patch(gpt_full_response,victim_file,polluter_file,victim_full_name,polluter_full_name,time):
    v_file = open(victim_file, 'r', errors='ignore')
    victim_test_class = v_file.read()
    p_file = open(polluter_file, 'r', errors='ignore')
    polluter_test_class = p_file.read()
    patch = {
        "victim":{"code":{"fields":{}, "methods":{}}, "import":[], "pom":"", "toreplace":{"field_names":[], "method_names":[]}},
        "polluter":{"code":{"fields":{}, "methods":{}}, "import":[], "pom":"", "toreplace":{"field_names":[], "method_names":[]}}    
        }
    # patch = {"code":{"fields":{}, "methods":{}}, "import":[], "pom":"", "toreplace":{"field_names":[], "method_names":[]}}
    response = gpt_full_response.replace("```java","").replace("```","")
    
    print(time, victim_full_name, "process response =======================\n",flush=True)
    print(response,flush=True)
    print(time, victim_full_name,"process response =======================\n",flush=True)
    
    potential_match_final = response
    response_noimp = potential_match_final
    static_import_pattern = re.compile(r"import\s+(static\s+)?([\w\.]+(\.\*)?);", re.MULTILINE)
    static_imp_matches = static_import_pattern.findall(potential_match_final)
    orig_imp_matches = static_import_pattern.findall(victim_test_class)
    orig_imps = []
    for orig_match in orig_imp_matches:
        imp_stat = ""
        if orig_match[0].strip() == "static" and orig_match[1] != '':
            imp_stat = "import static " + orig_match[1] + ";"
        elif orig_match[0].strip() == "" and orig_match[1] != '':
            imp_stat = "import " + orig_match[1] + ";"
        orig_imps.append(imp_stat)
    orig_imps_str = "\n".join(orig_imps)

    orig_imp_matches_p = static_import_pattern.findall(polluter_test_class)
    orig_imps = []
    for orig_match in orig_imp_matches_p:
        imp_stat = ""
        if orig_match[0].strip() == "static" and orig_match[1] != '':
            imp_stat = "import static " + orig_match[1] + ";"
        elif orig_match[0].strip() == "" and orig_match[1] != '':
            imp_stat = "import " + orig_match[1] + ";"
        orig_imps.append(imp_stat)
    orig_imps_str_p = "\n".join(orig_imps)
        
    for imp_match in static_imp_matches:
        if imp_match[0].strip() == "static" and imp_match[1] != '':
            imp_stat = "import static " + imp_match[1] + ";"
        elif imp_match[0].strip() == "" and imp_match[1] != '':
            imp_stat = "import " + imp_match[1] + ";"
        simp_name = imp_stat.split(".")[-1]
        response_noimp = potential_match_final.replace(imp_stat,"")
        potential_match_final = response_noimp
        if imp_stat not in victim_test_class and "." + simp_name not in orig_imps_str:
            print("will add ",imp_stat,flush=True)
            patch["victim"]["import"].append(imp_stat.replace("\n","").replace(";","")+";\n ")
        if imp_stat not in polluter_test_class and "." + simp_name not in orig_imps_str_p:
            print("will add ",imp_stat,flush=True)
            patch["polluter"]["import"].append(imp_stat.replace("\n","").replace(";","")+";\n ")
        else:
            print("not add", imp_stat)
    
    java_methods,parsed_format = utils.extract_java_code(response_noimp)
    if parsed_format == True:
        for method in java_methods:
            method_name = method[2]
            method_code = method[3]
            final_method_code = method_code
            node = method[4]
            if node.annotations != None:
                for ele in node.annotations:
                    tmp = "@"+ ele.name + final_method_code
                    final_method_code = tmp
            if method_name not in patch["victim"]["code"]["methods"]:
                patch["victim"]["code"]["methods"][method_name] = final_method_code
                patch["victim"]["toreplace"]["method_names"].append(method_name)
            if method_name not in patch["polluter"]["code"]["methods"]:
                patch["polluter"]["code"]["methods"][method_name] = final_method_code
                patch["polluter"]["toreplace"]["method_names"].append(method_name)

    if "<!-- <pom.xml start> -->" in response and "<!-- <pom.xml end> -->" in response:
        pom_stat = (response.split("<!-- <pom.xml start> -->")[1]).split("<!-- <pom.xml end> -->")[0]
        patch["victim"]["pom"] = pom_stat

    print(time, victim_full_name, "parsed patch=======================\n",flush=True)
    print(patch,flush=True)
    print(time, victim_full_name,"parsed patch=======================\n",flush=True)
    # exit(0)
    return patch

def apply_patch(project,sha,module,polluter,victim,test_type,patch,polluter_file,victim_file,cloneDir,updated_helper_res):
    # # print(patch)
    # print(project,sha,module,polluter,victim,test_type,patch,polluter_file,victim_file,cloneDir,updated_helper_res)
    # exit(0)

    for pv in patch:
        print(pv)
        for key in patch[pv]:
            print(patch[pv][key])
    print(updated_helper_res)
    victim_format_test = extract_fixes.replace_last(victim, '.', '#')
    polluter_format_test = extract_fixes.replace_last(polluter, '.', '#')

    if patch == None:
        print("[ERROR]No Patch",flush = True)
        return None
    try:
        file = open(victim_file, 'r', errors='ignore')
        victim_class_content = file.read()
        victim_fixed_class = victim_class_content
        for pv in ["victim"]:
            for key in updated_helper_res[pv]:
                for f_method in patch[pv]["code"]["methods"]: # here "victim" should bd pv
                    added = False
                    if key == "method_names" or key == "global_vars":
                        continue
                    else:
                        if f_method in updated_helper_res[pv][key]:
                            old_method = updated_helper_res[pv][key][f_method]
                            new_method = patch[pv]["code"]["methods"][f_method]
                            victim_fixed_class = victim_class_content.replace(old_method,new_method)
                            victim_class_content = victim_fixed_class
                            print(f_method, "victim changed to:\n", new_method)
                            added = True
        if polluter_file == victim_file:
            for pv in ["victim"]:
                for key in updated_helper_res["polluter"]:
                    for f_method in patch[pv]["code"]["methods"]: # here "victim" should bd pv
                        added = False
                        if key == "method_names" or key == "global_vars":
                            continue
                        else:
                            if f_method in updated_helper_res["polluter"][key]:
                                old_method = updated_helper_res["polluter"][key][f_method]
                                new_method = patch[pv]["code"]["methods"][f_method]
                                victim_fixed_class = victim_class_content.replace(old_method,new_method)
                                victim_class_content = victim_fixed_class
                                print(f_method, "polluter changed to:\n", new_method)
                                added = True

                    
        if len(patch["victim"]["import"]) > 0:
            package = utils.get_package(victim_class_content)
            if package != None:
                seq = victim_fixed_class.split(package)
                final_class = seq[0] + "\n" + package + "\n" + "\n".join(patch["victim"]["import"]) + "\n" + seq[1]
                print("added victim", patch["victim"]["import"])
            else:
                seq = victim_fixed_class.split("public class ")
                final_class = seq[0] + "\n".join(patch["victim"]["import"]) + "\n" + "public class " + seq[1]
        else:
            final_class = victim_fixed_class

        print(("[Applying FIX] Applying patch on test {}").format(victim_format_test),flush = True)
        f = open(victim_file, "w", errors='ignore')
        f.write(final_class)
        f.close()
        print("updated", victim_file)

        if polluter_file != victim_file:
            file = open(polluter_file, 'r', errors='ignore')
            polluter_class_content = file.read()
            polluter_fixed_class = polluter_class_content
            for pv in ["polluter"]:
                for key in updated_helper_res[pv]:
                    for f_method in patch[pv]["code"]["methods"]: # here "victim" should bd pv
                        added = False
                        if key == "method_names" or key == "global_vars":
                            continue
                        else:
                            if f_method in updated_helper_res[pv][key]:
                                old_method = updated_helper_res[pv][key][f_method]
                                new_method = patch[pv]["code"]["methods"][f_method]
                                polluter_fixed_class = polluter_class_content.replace(old_method,new_method)
                                polluter_class_content = polluter_fixed_class
                                print(f_method, "polluter changed to:\n", new_method)
                                added = True
                                print("old_method",old_method)
                                print("new_method",new_method)
                        
            if len(patch["polluter"]["import"]) > 0:
                package = utils.get_package(polluter_class_content)
                if package != None:
                    seq = polluter_fixed_class.split(package)
                    final_class = seq[0] + "\n" + package + "\n" + "\n".join(patch["polluter"]["import"]) + "\n" + seq[1]
                    print("added polluter", patch["polluter"]["import"])
                else:
                    seq = polluter_fixed_class.split("public class ")
                    final_class = seq[0] + "\n".join(patch["polluter"]["import"]) + "\n" + "public class " + seq[1]
            else:
                final_class = polluter_fixed_class

            print(("[Applying FIX] Applying patch on test {}").format(polluter_format_test),flush = True)
            f = open(polluter_file, "w", errors='ignore')
            f.write(final_class)
            f.close()
            print("updated", polluter_file)
        
        pom_path_v = ""
        if patch["victim"]["pom"] != "":
            print("pom need to update")
            dep2add = patch["victim"]["pom"]
            deps = dep2add
            if "<dependencies>" in patch["victim"]["pom"]:
                dep2add  = patch["victim"]["pom"].replace("<dependencies>","")
            if "</dependencies>" in dep2add:
                deps = dep2add.replace("</dependencies>","")
            if "/src/" in victim_file:
                root_path = victim_file.split("/src/")[0]
                pom_path = os.path.join(root_path,"pom.xml")
                if os.path.exists(pom_path):
                    extract_fixes.git_stash(project, sha, cloneDir,pom_path)
                    update_pom.add_dependency(pom_path,deps)
                    print("pom updated")
                    pom_path_v = pom_path
        if polluter_file != victim_file:
            if patch["polluter"]["pom"] != "":
                print("polluter pom need to update")
                dep2add = patch["polluter"]["pom"]
                deps = dep2add
                if "<dependencies>" in patch["polluter"]["pom"]:
                    dep2add  = patch["polluter"]["pom"].replace("<dependencies>","")
                if "</dependencies>" in dep2add:
                    deps = dep2add.replace("</dependencies>","")
                if "/src/" in polluter_file:
                    root_path_p = polluter_file.split("/src/")[0]
                    pom_path_p = os.path.join(root_path_p,"pom.xml")
                    if pom_path_p != pom_path_v:
                        if os.path.exists(pom_path):
                            extract_fixes.git_stash(project, sha, cloneDir,pom_path_p)
                            update_pom.add_dependency(pom_path_p,deps)
                            print("polluter pom updated")
        return final_class
    except:
        return None


def ask_gpt(test_list,save_resfile,cloneDir,save_dir,final_resfile):
    encoding = tiktoken.encoding_for_model("gpt-4")

    fields = ["project_url","project_name","sha","module","type","status", "PR_link","notes", 
              "polluter", "victim","polluter_file","victim_file",
              "patch","patch_file",
              "gpt_full_response","gpt_prompt","is_patched","result"]

    index = 0
    print("Len:", len(test_list),flush=True)
    com_err = []
    test_failure = []
    unfixed_test = test_list.copy() #initial unfixed_test includes all tests

    for test in test_list:
        print(test["victim"])

    with open(save_resfile, 'w', newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fields)
        writer.writeheader()
        for test in test_list:
            print("***", test["victim"])
            index += 1
            original_test = test.copy()
            done = False
            patch_is_none = False
            ans_chain = {}
            time = 0
            identical_err = 0
            test["result"] = []
            try:
            # if True:
                print(("[Before fix] Running victim {} with type {} from project {} sha {} module {}"
                    ).format(test["victim"], test["type"], test["project_name"], test["sha"], test["module"]),flush = True)

                extract_fixes.git_stash(test["project_name"], test["sha"], cloneDir,test["victim_file"])
                extract_fixes.restore_project(test["project_name"], test["sha"], cloneDir)
                victim_format_test = extract_fixes.replace_last(test["victim"], '.', '#')
                polluter_format_test = extract_fixes.replace_last(test["polluter"], '.', '#')
                print(test["type"],test["project_name"],test["sha"],polluter_format_test,victim_format_test,test["module"],cloneDir,"BeforeFix","1",test["polluter_file"],test["victim_file"])
                msg, res, original_failure_code,surefire_output = output_surefire(test["type"],test["project_name"],test["sha"],test["module"],polluter_format_test,victim_format_test,cloneDir,"BeforeFix","1",test["polluter_file"],test["victim_file"])
                print("time:", time, test["victim"], msg, res,flush=True)
                res_str = str(time) + ":" + res
                test["result"].append(res_str)
                helper_res = parse_helper_methods(test)
                # print(helper_res)
                # failure_code,failure_lines,updated_helper_res,err_methods 
                err_res = locate_err(surefire_output,test["polluter_file"],test["victim_file"],polluter_format_test,victim_format_test,helper_res)
                # print(err_res)
                failure_code = err_res["polluter"]["failure_code"] + err_res["victim"]["failure_code"]
                print("****")
                print(err_res)
                print("****")
                # print(err_res["victim"]["helper_res"])
                # print(err_res["polluter"]["helper_res"])
                updated_helper_res = err_res["victim"]["helper_res"]
                err_methods =  err_res["polluter"]["method_names"] + err_res["victim"]["method_names"]
                print(failure_code,updated_helper_res,err_methods)

                # exit(0)
                # 0 - before fix
                if time not in ans_chain:
                    ans_chain[time] = [msg,res]
                if res == "COMPILATION ERROR" or res == "BUILD FAILURE":
                    print("original test not compilable, or build failure, or incorrect test name")
                    done = True
                    print(("[original test not compilable] time {} Fix polluter {} and victim {} with type {} from project {} sha {} module {} \
                            ").format(time, test["polluter"], test["victim"],test["type"], test["project_name"], test["sha"], test["module"]),flush = True)  
                    test["result"].append("original test not compilable, or build failure, or incorrect test name")
                    write_final_info(test,final_resfile)
                    unfixed_test.remove(test)
                    continue
                if res == "test pass":
                    print("original test not flaky")
                    print(("[original test not flaky] time {} Fix polluter {} and victim {} with type {} from project {} sha {} module {} \
                                        ").format(time, test["polluter"],test["victim"], test["type"], test["project_name"], test["sha"], test["module"]),flush = True)  
                    done = True
                    test["result"].append("original test not flaky")
                    write_final_info(test,final_resfile)
                    unfixed_test.remove(test)
                    continue
                last_msg = msg
                
                if "OD" in test["type"]:
                    # 1 - first fix
                    time += 1
                    if time not in ans_chain:
                        ans_chain[time] = []
                        test,response,prompt,patch = generate_OD_patch(test,index,writer,None,last_msg,None,time,failure_code,updated_helper_res,err_methods)
                        print(prompt,response,flush=True)
                        # exit(0)
                        if patch != None: # apply fix, run nondex
                        #def apply_patch(project,sha,module,polluter,victim,test_type,patch,polluter_file,victim_file,,cloneDir,updated_helper_res):
                            final_class = apply_patch(test["project_name"],test["sha"],test["module"],test["polluter"],test["victim"],test["type"],patch,test["polluter_file"],test["victim_file"],cloneDir,updated_helper_res)
                            print(("[After fix] time {} Running test {} with type {} from project {} sha {} module {} \
                        ").format(time, test["victim"], test["type"], test["project_name"], test["sha"], test["module"]),flush = True)
                            # print("************************fixed class\n",final_class,"************************fixed class\n")
                            #output_surefire(test_type,project,sha,module,polluter_format_test,victim_format_test,cloneDir,tag,times,polluter_file,victim_file):
                            msg, res, failure_code,surefire_output = output_surefire(test["type"],test["project_name"],test["sha"],test["module"],polluter_format_test,victim_format_test,cloneDir,"AfterFix","1",test["polluter_file"],test["victim_file"])
                            print(msg, res, failure_code,surefire_output)
                            # exit(0)
                            helper_res = parse_helper_methods(test)
                            # failure_code,failure_lines,updated_helper_res,err_methods 
                            err_res = locate_err(surefire_output,test["polluter_file"],test["victim_file"],polluter_format_test,victim_format_test,helper_res)
                            print("****")
                            # print(err_res)
                            print("****")
                            # print(err_res["victim"]["helper_res"])
                            # print(err_res["polluter"]["helper_res"])
                            updated_helper_res = err_res["victim"]["helper_res"]
                            failure_code = err_res["polluter"]["failure_code"] + err_res["victim"]["failure_code"]
                            err_methods =  err_res["polluter"]["method_names"] + err_res["victim"]["method_names"]
                            print(failure_code,updated_helper_res,err_methods)
                            ans_chain[time] = [msg,res]
                            print("time:", time, msg, res,flush=True)
                            # exit(0)
                            last_msg = msg
                            last_patch = patch["victim"]["code"]
                            first_patch = patch["victim"]["code"]
                            res_str = str(time) + ":" + res
                            test["result"].append(res_str)
                            if res == "test pass":
                                print(("[****GOOD FIX*****] time {} Fix test {} with type {} from project {} sha {} module {} \
                                        ").format(time, test["victim"], test["type"], test["project_name"], test["sha"], test["module"]),flush = True)  
                                patch_file = write_patch(save_dir,test["victim"],test["project_name"],test["sha"],test["module"],patch,time)
                                test["patch_file"] = patch_file
                                test["result"].append("summary:good fix")
                                write_final_info(test,final_resfile)
                                for time in ans_chain:
                                    print("SUMMARY",index,time,test["victim"], test["type"], test["project_name"], test["sha"], test["module"], ans_chain[time],flush=True)
                                done = True
                                unfixed_test.remove(test)
                                continue
                            else:
                                if res == "BUILD FAILURE":
                                    extract_fixes.restore_project(test["project_name"], test["sha"], cloneDir)
                                # more try with feedback
                                for time in range(2, 6):
                                    if time not in ans_chain:
                                        ans_chain[time] = []
                                        test,response,prompt,patch = generate_OD_patch(test,index,writer,last_msg,None,last_patch,time,failure_code,updated_helper_res,err_methods)
                                        print(prompt,response,flush=True)
                                        if patch != None: # apply fix, run nondex
                                            final_class = apply_patch(test["project_name"],test["sha"],test["module"],test["polluter"],test["victim"],test["type"],patch,test["polluter_file"],test["victim_file"],cloneDir,updated_helper_res)
                                            print(("[After fix] time {} Running test {} with type {} from project {} sha {} module {} \
                                        ").format(time, test["victim"], test["type"], test["project_name"], test["sha"], test["module"]),flush = True)
                                            # print("************************fixed class\n",final_class,"************************fixed class\n")

                                            msg, res, new_failure_code,surefire_output = output_surefire(test["type"],test["project_name"],test["sha"],test["module"],polluter_format_test,victim_format_test,cloneDir,"AfterFix","1",test["polluter_file"],test["victim_file"])
                                            print(msg, res, new_failure_code,surefire_output)
                                            # exit(0)
                                            helper_res = parse_helper_methods(test)
                                            # new_failure_code,failure_lines,updated_helper_res,err_methods = locate_err(surefire_output,test["polluter_file"],test["victim_file"],polluter_format_test,victim_format_test,helper_res)
                                            err_res = locate_err(surefire_output,test["polluter_file"],test["victim_file"],polluter_format_test,victim_format_test,helper_res)
                                            updated_helper_res = err_res["victim"]["helper_res"]
                                            failure_code = err_res["polluter"]["failure_code"] + err_res["victim"]["failure_code"]
                                            err_methods =  err_res["polluter"]["method_names"] + err_res["victim"]["method_names"]
                                            print(failure_code,updated_helper_res,err_methods)
                                            print("time:", time, msg, res,flush=True)
                                            ans_chain[time]=[msg,res]
                                            res_str = str(time) + ":" + res
                                            test["result"].append(res_str)
                                            if res == "test pass": 
                                                done = True
                                                print(("[****GOOD FIX*****] time {} Fix test {} with type {} from project {} sha {} module {} \
                                        ").format(time, test["victim"], test["type"], test["project_name"], test["sha"], test["module"]),flush = True) 
                                                patch_file = write_patch(save_dir,test["victim"],test["project_name"],test["sha"],test["module"],patch,time)
                                                test["patch_file"] = patch_file
                                                test["result"].append("summary:good fix")
                                                write_final_info(test,final_resfile)
                                                for time in ans_chain:
                                                    print("SUMMARY",index,time,test["victim"], test["type"], test["project_name"], test["sha"], test["module"], ans_chain[time],flush=True)
                                                unfixed_test.remove(test)
                                                break
                                            else: 
                                                if res == "BUILD FAILURE":
                                                    extract_fixes.restore_project(test["project_name"], test["sha"], cloneDir)
                                                if last_msg == msg:
                                                    identical_err += 1
                                                last_msg = msg
                                                failure_code = new_failure_code
                                                if patch["victim"]["code"] != "":
                                                    last_patch = patch["victim"]["code"]
                                                else:
                                                    last_patch = first_patch
                                        else:
                                            print(time, "patch is none, reuse patch from last time",flush=True)
                                            break
                                            
                        else:
                            if test == None:
                                print("original test code not found",test)
                                done = True
                                unfixed_test.remove(original_test)
                                original_test["result"].append("original test code extraction error")
                                write_final_info(original_test,final_resfile)
                            else:
                                print("1st patch parsed with error",patch,flush=True)
                                patch_is_none = True
                                done = True
                                test["result"].append("1st patch is none")
                                write_final_info(test,final_resfile)
                            continue
               
            except Exception as e: #openai.error.InvalidRequestError
            # if True:
                print("********** START #{}".format(index), datetime.datetime.now(), test["project_name"], test["module"], test["victim"], "*************************************",flush = True)
                print("ERROR", e,flush = True)
                print("*EXCEPTION*")
                print(("[****BAD FIXES ***_other_exception_**] Fix test {} with type {} from project {} sha {} module {} \
                    ").format(test["victim"], test["type"], test["project_name"], test["sha"], test["module"]),flush = True)  
                test["result"].append(e)
                unfixed_test.remove(test)
                done = True
                write_final_info(test,final_resfile)
                print("*********** END #{}".format(index), datetime.datetime.now(), test["project_name"], test["module"], test["victim"], "*************************************",flush = True)
            
            if done == False:            
                categary = []
                for time in ans_chain:
                    print("SUMMARY",index,time,test["victim"], test["type"], test["project_name"], test["sha"], test["module"], ans_chain[time],flush=True)
                    if time != 0:
                        if len(ans_chain[time]) >= 2:
                            categary.append(ans_chain[time][1])

                if "test failures" in categary:
                    test["result"].append("summary:test_failures")
                    write_final_info(test,final_resfile)
                    test_failure.append(test)
                    print("*TESTFAIL*")
                    print(("[****BAD FIXES ***_test_fail_**] Fix test {} with type {} from project {} sha {} module {} \
                        ").format(test["victim"], test["type"], test["project_name"], test["sha"], test["module"]),flush = True)  
                else:
                    if "COMPILATION ERROR" in categary:
                        test["result"].append("summary:compilation_error")
                        write_final_info(test,final_resfile)
                        com_err.append(test)
                        print("*COMPERR*")
                        print(("[****BAD FIXES ***_compilation_error_**] Fix test {} with type {} from project {} sha {} module {} \
                            ").format(test["victim"], test["type"], test["project_name"], test["sha"], test["module"]),flush = True)
    print("=========compile error:", len(com_err), "\n", "===============test failures", len(test_failure))
    return unfixed_test

        
def generate_OD_patch(test,index,writer,err_msg,orig_surefire_msg,last_patch,time,failure_code,updated_helper_res,err_methods):
    victim_file_path = test["victim_file"]
    file = open(victim_file_path, 'r', errors='ignore')
    victim_test_class = file.read()
    victim_method_name = test["victim"].split(".")[-1]
    victim_test = utils.get_test_method(victim_method_name,victim_test_class)
    if victim_test == None:
        print("********** START #{}".format(index), datetime.datetime.now(), test["project_name"], test["module"], test["victim"], "*************************************",flush = True)
        print("ERROR when extracting victim test", flush = True)
        print("*********** END #{}".format(index), datetime.datetime.now(), test["project_name"], test["module"], test["victim"], "*************************************",flush = True)
        return None,None,None,None
    print("********** time {} ASK GPT START #{}".format(time, index), datetime.datetime.now(), test["project_name"], test["module"], test["victim"], "*************************************",flush = True)
    if err_msg == None and last_patch == None:
        test,response,prompt = gpt_fix_OD(test,orig_surefire_msg,failure_code,updated_helper_res,err_methods)
    if orig_surefire_msg == None:
        test,response,prompt = gpt_fix_err_OD(test,err_msg,last_patch,failure_code,updated_helper_res,err_methods)
    if test != None :
        patch = parse_patch(test["gpt_full_response"],test["victim_file"],test["polluter_file"],test["victim"],test["polluter"],time)
        if patch != None:
            test["is_patched"] = True
        else:
            test["is_patched"] = False
            print("no patch here, or patch failed to parse")
            return test,response,prompt,None
        test["gpt_prompt"] = prompt
        test["patch"] = patch
        info = test.copy()
        for key in info:
            print(key)
        writer.writerow(info)
    print("********** time {} GPT ANSWER END #{}".format(time, index), datetime.datetime.now(), test["project_name"], test["module"], test["victim"], "*************************************",flush = True)
    test["patch"] = patch
    return test,response,prompt,patch 

# def write_item(item_dict, save_resfile):

#     fields = ["project","sha","module","victim_file", \
#         "test","type","method_name", \
#         "gpt_full_response", "patch","gpt_prompt","status","PR_link","notes","patch_file"]

#     with open(save_resfile, 'w', newline="") as csvfile:
#         writer = csv.DictWriter(csvfile, fieldnames=fields)
#         writer.writeheader()
#         # for row in item_dict:
#         #     writer.writerow(row)

def write_patch(dir,test,project,sha,module,patch,time):
    patch_dir = os.path.join(dir,project,sha,module,test)
    Path(patch_dir).mkdir(parents=True, exist_ok=True)
    patch_file = os.path.join(patch_dir,str(time)+".patch")
    # patch = {
    # "victim":{"code":{"fields":{}, "methods":{}}, "import":[], "pom":"", "toreplace":{"field_names":[], "method_names":[]}},
    # "polluter":{"code":{"fields":{}, "methods":{}}, "import":[], "pom":"", "toreplace":{"field_names":[], "method_names":[]}}    
    # }
    file = open(patch_file, 'w')
    file.close()
    for pv in patch:
        for key in patch[pv]:
            file = open(patch_file, 'a')
            file.write(pv + "\n:" + key + ":\n" + str(patch[pv][key]))
            file.close()
    return patch_file

def write_final_info(test,final_resfile):
    info = test.copy()
    for key in ["test_class_content", "method_name","project", "patch","gpt_prompt","gpt_full_response"]:
        if key in info:
            info.pop(key)
    fields = ["project_url","project_name","sha","module", "polluter","victim","type", \
        "status", "PR_link","notes","polluter_file",\
        "victim_file","is_patched","patch_file","result"]
    with open(final_resfile, 'a', newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fields)
        writer.writerow(info)

def extract_test_method(test_name, class_content):
    res = utils.get_test_method(test_name, class_content)
    if res == None:
        return None
    test_method = res[3]
    return test_method

if __name__ == "__main__":
    args = sys.argv[1:]
    pr_csv = args[0]
    clone_dir = args[1]
    api_key = args[2]
    save_resfile = args[3]
    final_resfile = args[4]
    save_dir = args[5]
    unfixed_csv = args[6]

    openai.api_key = api_key
    openai.organization = os.getenv("OPENAI_ORGANIZATION")
    test_list = get_uniq_projects.pv_collect_tests(pr_csv)
    unfixed_test = ask_gpt(test_list,save_resfile,clone_dir,save_dir,final_resfile)
    sample_tests.od_filter_tests(unfixed_test,unfixed_csv)
    # for item in unfixed_test:
        # print("unfixed: ", item)
