import csv
import sys
import os
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
import diff_match_patch as dmp_module
import difflib

run_nondex_cmds = "/home/azureuser/flaky/cmds/run_nondex.sh"
checkout_project_cmds = "/home/azureuser/flaky/cmds/checkout_project.sh"

def generate_input(clone_dir,tests):
    test_list = []
    for tag in tests:
        test_info = {"project":'',"sha":'',"module":'',"file_path":'', \
        "test":'',"type":'',"test_class_content":'',"method_name":'', \
        "status": '',"PR_link":'',"notes":'',"project_url":'',"patch_file":'',
        "patch_file":"","result":[]
        }

        # print(tag)
        project_url = tests[tag]["project"]
        name = tests[tag]["name"]
        sha = tests[tag]["sha"]
        modules =  tests[tag]["module_tests"]
        type = tests[tag]["type"]
        status = tests[tag]["status"]
        pr = tests[tag]["PR_link"]
        notes = tests[tag]["notes"]
        
        for module in modules:
            for test in modules[module]:
                dir_list = []
                if test == None:
                    continue
                class_name = test.split(".")[-2]
                project_dir = os.path.join(clone_dir,sha,name)
                for root, dirs, files in os.walk(project_dir):
                    for file in files:
                        file_path = os.path.join(root,file)
                        test_path = "/".join(test.split(".")[:-1])
                        if file_path.endswith(".java") and file == class_name+".java" \
                            and "/test/" in file_path and test_path in file_path:
                                if file_path not in dir_list:
                                    dir_list.append(file_path)

                file_path_fd = False                    

                for file_path in dir_list:
                    method_name = test.split(".")[-1]
                    if os.path.exists(file_path):
                            with open(file_path,encoding="utf8", errors='ignore') as f:
                                content = f.read()
                                if method_name+"(" in content:
                                    test_info = {"project_url":project_url, "project":name ,"sha":sha ,"module":module ,"file_path":file_path, \
                                                 "status": status,"PR_link":pr,"notes":notes, "patch_file":"","result":[], "patch":"", \
                                    "test":test,"type":type,"test_class_content":content,"method_name":test.split(".")[-1]}
                                    test_list.append(test_info)
                                    file_path_fd = True
                                    continue
                     
                if file_path_fd == False:
                    test_info = {"project_url":project_url,"project":name ,"sha":sha ,"module":module ,"file_path":"", \
                                 "status": status,"PR_link":pr,"notes":notes, "patch_file":"","result":[], "patch":"",\
                                    "test":test,"type":type,"test_class_content":"","method_name":test.split(".")[-1]}
                    
                    print("[ERROR] File Not found:", dir_list, test, flush = True)
                    print(method_name,flush=True)
                    # print(content)
                    
    return test_list

def gpt_fix_err(test,test_content,err_msg,last_patch,failure_code):
    test_method = test["method_name"]
    test_type = test["type"].split(";")[0]
    test["gpt_full_response"] = ""
    test["patch"] = ""
    test["patch_file"] = ""
    ID_description = ""
    ID_API = "ID flaky tests are caused by using some APIs which assume the order of elements are guaranteed, \
        such as HashSet, HashMap, toString(), etc. \
        You should change APIs which do not guarantee orders. \
        A common fix is to use APIs which can make sure the elements are in deterministic order,such as LinkedHashSet, LinkedHashMap, JsonParser, etc.; \
        Or to make sure the elements from those APIs are in order. But if you didn't find similar cases, you should fix by other ways, just to make sure the test will always pass."
    ID_notFoundAPI = "Make sure the test can always pass. Make sure all APIs can return elements in deterministic order."
    
    NOD_additional = "NOD flaky tests are non-order-dependent, they can be flaky due to any reason other than solely \
        depending on test orders. They can be flaky due to concurrency, timeout, platform dependency, \
        timezone dependency, etc. But if you didn't find similar cases, you should fix it by other ways, make sure it will always pass deterministically."
    code = []
    potential_lines = process_line.get_potential_API(last_patch)
    for api in potential_lines:
        code.extend(potential_lines[api])
    if failure_code != None :
        failure_code_str = "\t".join(failure_code)
    if len(code) > 0: #or "expected" in failure_code_str or "but found" in failure_code_str or "but was" in failure_code_str:
        ID_additional = ID_API
    else:
        ID_additional = ID_API

    if failure_code != None :
        if len(failure_code) > 0:
            ID_description = "\n Lines \"{}\" cause the flakiness. Fix it. {}".format(("\n".join(failure_code)).strip(),ID_additional)
        else:
            ID_description = "\n Lines \"{}\" may cause the flakiness. Fix it. {}".format(("\n".join(code)).strip(),ID_additional)
    else:
        ID_description = "\n Lines \"{}\" may cause the flakiness. Fix it. {}".format(("\n".join(code)).strip(),ID_additional)
    
    NOD_description = NOD_additional
    if failure_code != None :
        NOD_description = "\n Lines \"{}\" cause the flakiness. Fix it. {}".format(("\n".join(failure_code)).strip(),NOD_additional)
    description_dict = { "ID": ID_description, "NOD":NOD_description}

    prompt = "You are a software testing expert. To fix the original flaky test, the following code is from your previous answer {}, I received errors: {}, {}\
          fix the flakiness and keep the code in the same format: \
            only reply with all code inside one unique code block, \
                and nothing else. do not write explanations, do not put original method in your answer: \
                1) Fix the flakiness and print the complete method code of this test between //<fix start> and //<fix end>. \
                    Your code should be compilable without any errors. \
                    Make sure all the arguments are correct. \
                    Use compatible types for all variables. \
                    Do not define or write helper methods out of the test, make sure all methods you want to call are inside the test method. Do not use try-catch in your code.\
                2) Update dependencies in pom.xml if needed, \
                    put the code between <!-- <pom.xml start> --> and <!-- <pom.xml end> -->. \
                    Provide a specific version for the dependency you add. Do not add existing dependencies. Do not add my artifact in dependencies, do not include my artifact in your pom.xml code.\
                3) Update import list if needed,\
                    put the code between //<import start> and //<import end>. \
                    Assume required classes for original code are setup correctly, \
                    do not include them in your code. \
                    ".format(last_patch,err_msg,description_dict[test_type])
    
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


def gpt_fix(test,test_content,orig_nondex_msg,failure_code):
    OD_description = "OD flaky tests are order-dependent, they are caused by shared states among tests. \
                The outcome depends on the test order in which they are run."
    NOD_additional = "NOD flaky tests are non-order-dependent, they can be flaky due to any reason other than solely \
        depending on test orders. They can be flaky due to concurrency, timeout, platform dependency, \
        timezone dependency, etc. But if you didn't find similar cases, you should fix it by other ways, make sure it will always pass deterministically."
    ID_description = ""
    ID_API = "ID flaky tests are caused by using some APIs which assume the order of elements are guaranteed, \
        such as HashSet, HashMap, toString(), etc. \
        You should change APIs which do not guarantee orders. \
        A common fix is to use APIs which can make sure the elements are in deterministic order,such as LinkedHashSet, LinkedHashMap, JsonParser, etc.; \
        Or to make sure the elements from those APIs are in order. But if you didn't find similar cases, you should fix by other ways, just to make sure the test will always pass."
    ID_notFoundAPI = "Make sure the test can always pass. Make sure all APIs can return elements in deterministic order."

    code = []
    potential_lines = process_line.get_potential_API(test_content)
    for api in potential_lines:
        code.extend(potential_lines[api])
    if failure_code != None :
        failure_code_str = "\t".join(failure_code)
    if len(code) > 0: #or "expected" in failure_code_str \
        # or "but found" in failure_code_str or "but was" in failure_code_str:
        ID_additional = ID_API
    else:
        ID_additional = ID_API

    if failure_code != None :
        if len(failure_code) > 0:
            ID_description = "\n Lines \"{}\" cause the flakiness. Fix it. {}".format(("\n".join(failure_code)).strip(),ID_additional)
        else:
            ID_description = "\n Lines \"{}\" may cause the flakiness. Fix it. {}".format(("\n".join(code)).strip(),ID_additional)
    else:
        ID_description = "\n Lines \"{}\" may cause the flakiness. Fix it. {}".format(("\n".join(code)).strip(),ID_additional)
    
    NOD_description = NOD_additional
    if failure_code != None :
        NOD_description = "\n Lines \"{}\" cause the flakiness. Fix it. {}".format(("\n".join(failure_code)).strip(),NOD_additional)
    description_dict = { "ID": ID_description, "NOD": NOD_description}
    
          
    NIO_description = "NIO tests are non-idempotent-outcome tests. \
        Each NIO test has side effects and self-pollutes the state shared among test runs. \
        A test is an NIO test if the test outcome (pass or fail) changes after repeated test runs, \
        due to the changes of the state shared among runs of the NIO test"
    
    UD_description = "Unknown Dependency tests that pass and fail in a test suite or in isolation"
    OSD_description = "Operating System Dependent tests that pass and fail depending on the operating system."
    NDOI_description = "Non-Deterministic Order-Independent tests that fail non-deterministically but similar failure rates in all orders."
    NDOD_description = "Non-Deterministic Order-Dependent tests that fail non-deterministically but with significantly different failure rates in different orders."

    description_dict = {"OD": OD_description, "NOD": NOD_description, "ID": ID_description,
                        "OD-Brit": OD_description, "OD-Vic": OD_description, "NIO": NIO_description,
                        "UD": UD_description, "OSD": OSD_description, "NDOI": NDOI_description, "NDOD":NDOD_description}

    test_method = test["method_name"]
    test_type = test["type"].split(";")[0]
    test["gpt_full_response"] = ""
    test["patch"] = ""
    test["patch_file"] = ""

    prompt = "I want you to fix a flaky test. {} is a flaky test of type {}, located in the following java class {}. \
                I got the following error when running NonDex on it: {}. {}\
                Follow steps below, I want you to only reply with all code inside one unique code block, do not write anything else. \
                do not write explanations. do not put original method in your answer.\
                1) Fix the flakiness and print the fixed complete method code of this test between //<fix start> and //<fix end>. \
                    Your code should be compilable without any errors. \
                    Make sure all the arguments are correct.\
                    Use compatible types for all variables. \
                    Do not define or write helper methods out of the test, make sure all methods you want to call are inside the test method. Do not use try-catch in your code.\
                2) Update dependencies in pom.xml if needed, \
                    put the code between <!-- <pom.xml start> --> and <!-- <pom.xml end> -->. \
                    Provide a specific version for the dependency you add. Do not add existing dependencies. Do not add my artifact in dependencies, do not include my artifact in your pom.xml code.\
                3) Update import list if needed,\
                    put the code between //<import start> and //<import end>. \
                    Assume required classes for original code are setup correctly, \
                    do not include them in your code. \
                    ".format(test_method,test_type,test_content,orig_nondex_msg,description_dict[test_type])
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

def output_nondex(test_type,project,sha,format_test,module,cloneDir,tag,times,file_path):
    output = extract_fixes.verify_by_tool(test_type,project,sha,format_test,module,cloneDir,tag,times)
    msg, res, failure_code = process_nondex_output(output,file_path,format_test)
    return "\n".join(msg), res, failure_code

def process_nondex_output(output,file_path,format_test):
    res = ""
    msg = []
    seq_list = output.split("\n")
    if "COMPILATION ERROR" in output:
        res = "COMPILATION ERROR"
        for line in seq_list:
            if "To see the full stack trace of the errors" in line:
                break
            if "ERROR" in line and "Help 1" not in line:
                simp_line = line.replace(file_path,"").replace("\x1b[1;31m","").replace("\x1b[m","").replace("\x1b[1m","").replace("\x1b[36m","").replace("\n", "\t").replace("[ERROR]","").strip()
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
        if "test failures" not in output and "BUILD SUCCESS" in output:
            o_seq = output.split("\n")
            for seq in o_seq:
                if "Tests run:" in seq and "Failures:" in seq and "Errors:" in seq:
                    seq2 = seq.replace(" ","").strip().replace("\t","").replace("\n","").replace(",","")
                    if "Testsrun:1Failures:0Errors:" in seq2:
                        return msg,"test pass",None

        #     #Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
        #     if "ERROR" in output:
        #         return msg,"BUILD FAILURE",None
            
        for pre_line in seq_list:
            line = pre_line.replace("\x1b[1;31m","").replace("\x1b[m","").replace("\x1b[1m","").replace("\x1b[36m","").strip()
            if "cannot find symbol" in line:
                tmp_seq = line.split(" ")[0]
                if "[" in tmp_seq and "]" in tmp_seq and "," in tmp_seq:
                    line = "cannot find symbol"
                    msg.append(line)
            if "There are test failures" in line:
                res = "test failures"
                msg.append(line)
            if "Failed tests:" in line:
                msg.append(line)
                res = "test failures"
            if "Tests in error:" in line:
                indx = seq_list.index(pre_line)
                msg.append(seq_list[indx+1])
                res = "test failures"

        s_list = output.split("<<< FAILURE!")[1:]
        for item in s_list:
            if "Results" in item and "Failures: 1" in item:
                add_info = item.split("Results")[0]
                if "at" in add_info:
                    err_info = add_info.split("\tat")[0]
                    if err_info not in msg:
                        msg.append(err_info.replace("\n","\t"))
            #Errors: 1
            if "Results" in item and "Errors: 1" in item:
                add_info = item.split("Results")[0]
                if "at" in add_info:
                    err_info = add_info.split("\tat")[0]
                    if err_info not in msg:
                        msg.append(err_info.replace("\n","\t"))
        if len(msg) == 0:
            if "BUILD SUCCESS" not in output:
                return msg,"BUILD FAILURE",None
            for pre_line in seq_list:
                line = pre_line.replace("\x1b[1;31m","").replace("\x1b[m","").replace("\x1b[1m","").replace("\x1b[36m","")
                if line.startswith("[ERROR]") and "Help 1" not in line and "Time elapsed:" not in line \
                    and "For more information about the errors " not in line and "To see" not in line and "Re-run Maven using the" not in line:
                    line.replace(file_path,"")
                    msg.append(line)
        failure_code,failure_lines = process_line.get_line_location_msg(output,file_path,format_test)
        if len(msg) > 0:
            uniq_msg = list(set(msg))
            return uniq_msg,res,failure_code
        else:
            if "BUILD SUCCESS" not in output:
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
        msg, res, failure_code = output_nondex(test_type,project,sha,format_test,module,cloneDir,tag,times,file_path)
    else:
        print("error when applying simple patch without processing")
    print(("[Simple patch end] Running test with simple patch {} with type {} from project {} sha {} module {}, simple result: {} \
                    ").format(test_fullname, test_type, project, sha, module,res),flush = True)
    extract_fixes.git_stash(project, sha, cloneDir,file_path)
    return res
    

def parse_patch(gpt_full_response,file_path,test_name,time):
    file = open(file_path, 'r', errors='ignore')
    test_class = file.read()

    patch = {"code":"", "import":[], "pom":""}
    response = gpt_full_response
    print(time, test_name, "process response =======================\n",flush=True)
    print(response,flush=True)
    print(time, test_name,"process response =======================\n",flush=True)

    code = response.replace("\n"," \n ")
    potential_match_final = ""
    if "//<fix start>" in code:
        potential_match = code.split("//<fix start>")[1]
        potential_match_final = potential_match
        if "//<fix end>" in code:
            potential_match_final = " \n " + potential_match.split("//<fix end>")[0] + " \n "
    elif "<fix start>" in code:
        potential_match = code.split("<fix start>",1)[1]
        potential_match_final = potential_match
        if "<fix end>" in code:
            potential_match_final = " \n " + potential_match.rsplit("<fix end>",1)[0] + " \n "
    if potential_match_final != "":
        import_pattern = re.compile(r'^\s*import\s+([\w.]+);', re.MULTILINE)
        p_imp_matches = import_pattern.findall(code)
        for match in p_imp_matches:
            tmp = "import " + match + ";"
            if tmp in potential_match_final:
                pfinal = potential_match_final.replace(tmp,"")
                potential_match_final = pfinal
        pleft = potential_match_final.count("{")
        pright = potential_match_final.count("}")
        if pleft == pright:
            if "public class " in potential_match_final:
                if "public void" in potential_match_final:
                    tmpstr = potential_match_final.split("public void ")[1]
                    k = tmpstr.rfind("}")
                    new_string = tmpstr[:k] + "\n"
                    final_match = "public void " + new_string
                    if final_match.count("{") == final_match.count("}"):
                        potential_match_final = final_match

                elif "void" in potential_match_final:
                    tmpstr = potential_match_final.split("void ")[1]
                    k = tmpstr.rfind("}")
                    new_string = tmpstr[:k] + "\n"
                    final_match = "public void " + new_string
                    if final_match.count("{") == final_match.count("}"):
                        potential_match_final = final_match

    regex = r"public\s+\w+\s+\w+\s*\([^)]*\)\s*(?:throws\s+\w+\s*)?\{(?:.|\n)*?\n\s*\}"
    void_regex = r'\bvoid\s+\w+\s*\([^)]*\)\s*(?:throws\s+\w+(?:,\s*\w+)*)?\s*{[^}]*}'
    method_pattern = re.compile(regex, re.DOTALL)
    void_method_pattern = re.compile(void_regex, re.DOTALL)
    matches = method_pattern.findall(code)
    void_matches = void_method_pattern.findall(code)
    if len(matches) >= 1:
        for match in matches:
            if test_name in match:
                leftc = match.count("{")
                rightc = match.count("}")
                if leftc == rightc and leftc > 0:
                    patch["code"] = match +" \n "
                    print(leftc,rightc)
                    print("\n match start by regex -----------------------------\n",test_name,"\n", match,"\n match end-----------------------------\n")
                    break
                elif potential_match_final != "":
                    leftcp = potential_match_final.count("{")
                    rightcp = potential_match_final.count("}")
                    if leftcp == rightcp and leftcp > 0:
                        patch["code"] = potential_match_final +" \n "
                        print(leftcp,rightcp)
                        print("\n match start by string match -----------------------------\n",test_name,"\n",potential_match_final,"\n match end-----------------------------")
                        break
    elif len(void_matches) >= 1:
        for match in void_matches:
            if test_name in match:
                leftc = match.count("{")
                rightc = match.count("}")
                if leftc == rightc and leftc > 0:
                    patch["code"] = match +" \n "
                    print(leftc,rightc)
                    print("\n match start by regex -----------------------------\n",test_name,"\n", match,"\n match end-----------------------------\n")
                    break
                elif potential_match_final != "":
                    leftcp = potential_match_final.count("{")
                    rightcp = potential_match_final.count("}")
                    if leftcp == rightcp and leftcp > 0:
                        patch["code"] = potential_match_final +" \n "
                        print(leftcp,rightcp)
                        print("\n match start by string match -----------------------------\n",test_name,"\n",potential_match_final,"\n match end-----------------------------")
                        break
    else:
        if potential_match_final != "":
            leftcp = potential_match_final.count("{")
            rightcp = potential_match_final.count("}")
            if leftcp == rightcp and leftcp > 0:
                patch["code"] = potential_match_final +" \n "
                print(leftcp,rightcp)
                print("\n match start by string match -----------------------------\n",test_name,"\n",potential_match_final,"\n match end-----------------------------")
    import_pattern = re.compile(r'^\s*import\s+([\w.]+);', re.MULTILINE)
    imp_matches = import_pattern.findall(code)
    static_import_pattern = re.compile(r"import\s+(static\s+)?([\w\.]+(\.\*)?);", re.MULTILINE)
    static_imp_matches = static_import_pattern.findall(code)
    code_list = code.split("\n")
    for code_piece in code_list:
        if "import " in code_piece and ";" in code_piece:
            ele = (code_piece.split("import")[1]).strip().replace(";","")
            if ele not in imp_matches and re.match(import_pattern, code_piece):
                imp_matches.append(ele)
                print("additional work:",ele,flush=True)
        if "import " in code_piece and ";" in code_piece and "static" in code_piece:
            ele = (code_piece.split("static")[1]).strip().replace(";","")
            if ele not in static_imp_matches and re.match(static_import_pattern, code_piece):
                static_imp_matches.append(ele)
                print("additional work:",ele,flush=True)
    
    print("************************")
    print(imp_matches,static_imp_matches)
    print("************************")
    orgl_imps_lst = import_pattern.findall(test_class)
    orgl_imps = ";\n".join(orgl_imps_lst) + ";\n"
    print("orgl_imps********",orgl_imps.replace("\n", "\t"))
    for imp_match in imp_matches:  
        imp_stat = "import " + imp_match + ";"
        simp_name = imp_stat.split(".")[-1]
        if imp_stat not in test_class and "." + simp_name not in orgl_imps:
            print("will add ",imp_stat,flush=True)
            patch["import"].append(imp_stat.replace("\n","").replace(";","")+";\n ")
        else:
            print("not add", imp_stat)
    for imp_match in static_imp_matches:
        if imp_match[0].strip() == "static" and imp_match[1] != '':
            imp_stat = "import static " + imp_match[1] + ";"
            simp_name = imp_stat.split(".")[-1]
            if imp_stat not in test_class and "." + simp_name not in orgl_imps:
                print("will add ",imp_stat,flush=True)
                patch["import"].append(imp_stat.replace("\n","").replace(";","")+";\n ")
            else:
                print("not add", imp_stat)

    if "<!-- <pom.xml start> -->" in response and "<!-- <pom.xml end> -->" in response:
        pom_stat = (response.split("<!-- <pom.xml start> -->")[1]).split("<!-- <pom.xml end> -->")[0]
        patch["pom"] = pom_stat

    print(time, test_name, "parsed patch=======================\n",flush=True)
    print(patch,flush=True)
    print(time, test_name,"parsed patch=======================\n",flush=True)

    return patch

def apply_patch(project,sha,module,test_fullname,test_type,method_name,patch,file_path,cloneDir):
    # print(patch)
    format_test = extract_fixes.replace_last(test_fullname, '.', '#')
    if patch == None:
        print("[ERROR]No Patch",flush = True)
        return None
    try:
        file = open(file_path, 'r', errors='ignore')
        class_content = file.read()
        res = utils.get_test_method(method_name, class_content) #res = [start,end,method_name,method_code,node.annotations]
        if res == None:
            return None
        method_code = res[3]
        fixed_class = class_content
        if patch["code"] != "":
            fixed_class = class_content.replace(method_code,patch["code"])
        
        if len(patch["import"]) > 0:
            package = utils.get_package(class_content)
            if package != None:
                seq = fixed_class.split(package)
                # print("*************")
                # print(seq[0],seq[1])
                final_class = seq[0] + "\n" + package + "\n" + "\n".join(patch["import"]) + "\n" + seq[1]
            else:
                seq = fixed_class.split("public class ")
                final_class = seq[0] + "\n".join(patch["import"]) + "\n" + "public class " + seq[1]
        else:
            final_class = fixed_class

        print("len:",len(patch["import"]),patch["import"],flush=True)
        print(("[Applying FIX] Applying patch on test {}").format(format_test),flush = True)
        f = open(file_path, "w", errors='ignore')
        f.write(final_class)
        f.close()

        if patch["pom"] != "":
            print("pom need to update")
            dep2add = patch["pom"]
            deps = dep2add
            if "<dependencies>" in patch["pom"]:
                dep2add  = patch["pom"].replace("<dependencies>","")
            if "</dependencies>" in dep2add:
                deps = dep2add.replace("</dependencies>","")
            if "/src/" in file_path:
                root_path = file_path.split("/src/")[0]
                pom_path = os.path.join(root_path,"pom.xml")
                if os.path.exists(pom_path):
                    extract_fixes.git_stash(project, sha, cloneDir,pom_path)
                    update_pom.add_dependency(pom_path,deps)
                    print("pom updated")
        return final_class
    except:
        return None


def ask_gpt(test_list,save_resfile,cloneDir,save_dir,final_resfile):
    encoding = tiktoken.encoding_for_model("gpt-4")
    fields = ["project_url","project","sha","module", "test","type", \
              "status", "PR_link","notes",
              "patch","method_name", \
                "gpt_full_response","file_path","gpt_prompt","is_patched","test_class_content","patch_file","result"]
    index = 0
    print("Len:", len(test_list),flush=True)
    # print(test_list)
    com_err = []
    test_failure = []
    unfixed_test = test_list.copy() #initial unfixed_test includes all tests

    with open(save_resfile, 'w', newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fields)
        writer.writeheader()
        for test in test_list:
            original_test_code = extract_test_method(test["method_name"], test["test_class_content"])
            index += 1
            print("start to run:", test["test"],test_list.index(test))
            original_test = test.copy()
            done = False
            patch_is_none = False
            ans_chain = {}
            time = 0
            identical_err = 0
            try:
            # if True:
                print(("[Before fix] Running test {} with type {} from project {} sha {} module {} \
                    ").format(test["test"], test["type"], test["project"], test["sha"], test["module"]),flush = True)
                extract_fixes.git_stash(test["project"], test["sha"], cloneDir,test["file_path"])
                extract_fixes.restore_project(test["project"], test["sha"], cloneDir)
                format_test = extract_fixes.replace_last(test["test"], '.', '#')
                msg, res, original_failure_code = output_nondex(test["type"],test["project"],test["sha"],format_test,test["module"],cloneDir,"BeforeFix","1",test["file_path"])
                print("time:", time,test["test"], msg, res,flush=True)
                res_str = str(time) + ":" + res
                test["result"].append(res_str)
                # 0 - before fix
                if time not in ans_chain:
                    ans_chain[time] = [msg,res]
                if res == "COMPILATION ERROR" or res == "BUILD FAILURE":
                    print("original test not compilable, or build failure, or incorrect test name")
                    done = True
                    print(("[original test not compilable] time {} Fix test {} with type {} from project {} sha {} module {} \
                                        ").format(time, test["test"], test["type"], test["project"], test["sha"], test["module"]),flush = True)  
                    test["result"].append("original test not compilable, or build failure, or incorrect test name")
                    write_final_info(test,final_resfile)
                    unfixed_test.remove(test)
                    continue
                if res == "test pass":
                    print("original test not flaky")
                    print(("[original test not flaky] time {} Fix test {} with type {} from project {} sha {} module {} \
                                        ").format(time, test["test"], test["type"], test["project"], test["sha"], test["module"]),flush = True)  
                    done = True
                    test["result"].append("original test not flaky")
                    write_final_info(test,final_resfile)
                    unfixed_test.remove(test)
                    continue
                last_msg = msg
                
                if test["type"] == "ID" or test["type"] == "NOD":
                    # 1 - first fix
                    time += 1
                    if time not in ans_chain:
                        ans_chain[time] = []
                        test,response,prompt,patch = generate_ID_patch(test,index,writer,None,last_msg,None,time,original_failure_code)
                        print(prompt,response,flush=True)

                        if patch != None: # apply fix, run nondex
                            # simple patch
                            simple_patch = simply_parse(response)
                            simple_res = apply_before_processing(test["project"],test["sha"],test["module"],test["test"],test["type"],test["method_name"],patch,test["file_path"],cloneDir,"AfterSimpleFix","1")
                            extract_fixes.git_stash(test["project"], test["sha"], cloneDir,test["file_path"])
                            extract_fixes.restore_project(test["project"], test["sha"], cloneDir)
                            res_str = "simple_result_before" + ":" + str(simple_res)
                            test["result"].append(res_str)
                            # simple patch end

                            final_class = apply_patch(test["project"],test["sha"],test["module"],test["test"],test["type"],test["method_name"],patch,test["file_path"],cloneDir)
                            print(("[After fix] time {} Running test {} with type {} from project {} sha {} module {} \
                        ").format(time, test["test"], test["type"], test["project"], test["sha"], test["module"]),flush = True)
                            # print("************************fixed class\n",final_class,"************************fixed class\n")
                            
                            msg, res, failure_code = output_nondex(test["type"],test["project"],test["sha"],format_test,test["module"],cloneDir,"AfterFix","1",test["file_path"])
                            ans_chain[time] = [msg,res]
                            print("time:", time, msg, res,flush=True)
                            last_msg = msg
                            last_patch = patch["code"]
                            first_patch = patch["code"]
                            res_str = str(time) + ":" + res
                            test["result"].append(res_str)
                            if res == "test pass":
                                print(("[****GOOD FIX*****] time {} Fix test {} with type {} from project {} sha {} module {} \
                                        ").format(time, test["test"], test["type"], test["project"], test["sha"], test["module"]),flush = True)  
                                patch_file = write_patch(save_dir,test["test"],test["project"],test["sha"],test["module"],patch,time,original_test_code)
                                test["patch_file"] = patch_file
                                test["result"].append("summary:good fix")
                                write_final_info(test,final_resfile)
                                for time in ans_chain:
                                    print("SUMMARY",index,time,test["test"], test["type"], test["project"], test["sha"], test["module"], ans_chain[time],flush=True)
                                done = True
                                unfixed_test.remove(test)
                                continue
                            else:
                                if res == "BUILD FAILURE":
                                    extract_fixes.restore_project(test["project"], test["sha"], cloneDir)
                                # more try with feedback
                                for time in range(2, 6):
                                    if time not in ans_chain:
                                        ans_chain[time] = []
                                        test,response,prompt,patch = generate_ID_patch(test,index,writer,last_msg,None,last_patch,time,failure_code)
                                        print(prompt,response,flush=True)
                                        if patch != None: # apply fix, run nondex
                                            final_class = apply_patch(test["project"],test["sha"],test["module"],test["test"],test["type"],test["method_name"],patch,test["file_path"],cloneDir)
                                            print(("[After fix] time {} Running test {} with type {} from project {} sha {} module {} \
                                        ").format(time, test["test"], test["type"], test["project"], test["sha"], test["module"]),flush = True)
                                            # print("************************fixed class\n",final_class,"************************fixed class\n")

                                            msg, res, new_failure_code = output_nondex(test["type"],test["project"],test["sha"],format_test,test["module"],cloneDir,"AfterFix","1",test["file_path"])
                                            print("time:", time, msg, res,flush=True)
                                            ans_chain[time]=[msg,res]
                                            res_str = str(time) + ":" + res
                                            test["result"].append(res_str)
                                            if res == "test pass": 
                                                done = True
                                                print(("[****GOOD FIX*****] time {} Fix test {} with type {} from project {} sha {} module {} \
                                        ").format(time, test["test"], test["type"], test["project"], test["sha"], test["module"]),flush = True) 
                                                patch_file = write_patch(save_dir,test["test"],test["project"],test["sha"],test["module"],patch,time,original_test_code)
                                                test["patch_file"] = patch_file
                                                test["result"].append("summary:good fix")
                                                write_final_info(test,final_resfile)
                                                for time in ans_chain:
                                                    print("SUMMARY",index,time,test["test"], test["type"], test["project"], test["sha"], test["module"], ans_chain[time],flush=True)
                                                unfixed_test.remove(test)
                                                break
                                            else: 
                                                if res == "BUILD FAILURE":
                                                    extract_fixes.restore_project(test["project"], test["sha"], cloneDir)
                                                if last_msg == msg:
                                                    identical_err += 1
                                                last_msg = msg
                                                failure_code = new_failure_code
                                                if patch["code"] != "":
                                                    last_patch = patch["code"]
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
                                print("1st patch is none",patch,flush=True)
                                patch_is_none = True
                                done = True
                                test["result"].append("1st patch is none")
                                write_final_info(test,final_resfile)
                            continue
               
            except Exception as e: #openai.error.InvalidRequestError
            # if True:
                print("********** START #{}".format(index), datetime.datetime.now(), test["project"], test["module"], test["method_name"], "*************************************",flush = True)
                print("ERROR", e,flush = True)
                print("*EXCEPTION*")
                print(("[****BAD FIXES ***_other_exception_**] Fix test {} with type {} from project {} sha {} module {} \
                    ").format(test["test"], test["type"], test["project"], test["sha"], test["module"]),flush = True)  
                test["result"].append(e)
                unfixed_test.remove(test)
                done = True
                write_final_info(test,final_resfile)
                print("*********** END #{}".format(index), datetime.datetime.now(), test["project"], test["module"], test["method_name"], "*************************************",flush = True)
            
            if done == False:            
                categary = []
                for time in ans_chain:
                    print("SUMMARY",index,time,test["test"], test["type"], test["project"], test["sha"], test["module"], ans_chain[time],flush=True)
                    if time != 0:
                        if len(ans_chain[time]) >= 2:
                            categary.append(ans_chain[time][1])

                if "test failures" in categary:
                    test["result"].append("summary:test_failures")
                    write_final_info(test,final_resfile)
                    test_failure.append(test)
                    print("*TESTFAIL*")
                    print(("[****BAD FIXES ***_test_fail_**] Fix test {} with type {} from project {} sha {} module {} \
                        ").format(test["test"], test["type"], test["project"], test["sha"], test["module"]),flush = True)  
                else:
                    if "COMPILATION ERROR" in categary:
                        test["result"].append("summary:compilation_error")
                        write_final_info(test,final_resfile)
                        com_err.append(test)
                        print("*COMPERR*")
                        print(("[****BAD FIXES ***_compilation_error_**] Fix test {} with type {} from project {} sha {} module {} \
                            ").format(test["test"], test["type"], test["project"], test["sha"], test["module"]),flush = True)
    print("=========compile error:", len(com_err), com_err, "\n", "===============test failures", len(test_failure))
    return unfixed_test

        
def generate_ID_patch(test,index,writer,err_msg,orig_nondex_msg,last_patch,time,failure_code):
    test_class = test["test_class_content"]
    test_content = extract_test_method(test["method_name"], test["test_class_content"])
    if test_content == None:
        # print(test)
        # print("original error here",test, flush=True)
        print("********** START #{}".format(index), datetime.datetime.now(), test["project"], test["module"], test["method_name"], "*************************************",flush = True)
        print("ERROR when extracting test method", flush = True)
        print("*********** END #{}".format(index), datetime.datetime.now(), test["project"], test["module"], test["method_name"], "*************************************",flush = True)
        return None,None,None,None
    print("********** time {} ASK GPT START #{}".format(time, index), datetime.datetime.now(), test["project"], test["module"], test["method_name"], "*************************************",flush = True)
    if err_msg == None and last_patch == None:
        test,response,prompt = gpt_fix(test,test_content,orig_nondex_msg,failure_code)
    if orig_nondex_msg == None:
        test,response,prompt = gpt_fix_err(test,test_content,err_msg,last_patch,failure_code)
    if test != None :
        patch = parse_patch(test["gpt_full_response"],test["file_path"],test["method_name"],time)
        if patch != None:
            test["is_patched"] = True
        else:
            test["is_patched"] = False
            print("no patch here")
            return test,response,prompt,None
        test["gpt_prompt"] = prompt
        test["patch"] = patch
        info = test.copy()
        info["test_class_content"] = time # record time in test_class_content
        writer.writerow(info)
    print("********** time {} GPT ANSWER END #{}".format(time, index), datetime.datetime.now(), test["project"], test["module"], test["method_name"], "*************************************",flush = True)
    test["patch"] = patch
    return test,response,prompt,patch 

def write_item(item_dict, save_resfile):

    fields = ["project","sha","module","file_path", \
        "test","type","method_name", \
        "gpt_full_response", "patch","gpt_prompt","status","PR_link","notes","patch_file"]

    with open(save_resfile, 'w', newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fields)
        writer.writeheader()
        # for row in item_dict:
        #     writer.writerow(row)

def write_patch(dir,test,project,sha,module,patch,time,original_test_code):
    dmp = dmp_module.diff_match_patch()
    patch_dir = os.path.join(dir,project,sha,module,test)
    Path(patch_dir).mkdir(parents=True, exist_ok=True)
    patch_file = os.path.join(patch_dir,str(time)+".patch")
    file = open(patch_file, 'w')
    file.write("test_before_fix:\n" + original_test_code + "\ntest_after_fix:\n")
    file.close()
    for key in patch:
        if key != "code":
            print(key)
            print(patch[key])
            file = open(patch_file, 'a')
            file.write("\n" + str(key) + ":\n" + str(patch[key]))
            file.close()
        else:
            d = difflib.Differ()
            diff = d.compare(original_test_code.strip().split("\n"), patch[key].strip().split("\n"))
            file = open(patch_file, 'a')
            file.write("\n" + str(key) + ":\n" + patch[key])
            # file.write("\n patch :\n" + '\n'.join(diff))
            file.close()
    return patch_file

def write_final_info(test,final_resfile):
    info = test.copy()
    for key in ["test_class_content", "method_name","project", "patch","gpt_prompt","gpt_full_response"]:
        if key in info:
            info.pop(key)
    fields = ["project_url","sha","module", "test","type", \
        "status", "PR_link","notes",\
        "file_path","is_patched","patch_file","result"]
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
    tests = get_uniq_projects.collect_tests(pr_csv)
    test_list = generate_input(clone_dir, tests)
    unfixed_test = ask_gpt(test_list,save_resfile,clone_dir,save_dir,final_resfile)
    sample_tests.filter_tests(unfixed_test,unfixed_csv)
    for item in unfixed_test:
        print("unfixed: ", item)