import javalang
from typing import Set, Tuple
import sys
import re


def get_helper_methods(code):
    method_list = parse_java_func_intervals(code)
    start_lines = []
    res = {"before":{},"after":{},"earlist_line":{},"method_names":[]}
    for method_info in method_list:
        start, end, method_name, method_code, node = method_info[0:]
        start_lines.append(start.line)
        if node.annotations != None:
            for ele in node.annotations:
                if ele.name == "BeforeClass" or ele.name == "Before" or ele.name == "BeforeAll":
                    if method_name not in res["before"]:
                        method_code = get_string(code,start,end)
                        res["before"][method_name] = method_code
                        res["method_names"].append(method_name)
                elif ele.name == "AfterClass" or ele.name == "After" or ele.name == "AfterAll":
                    if method_name not in res["after"]:
                        method_code = get_string(code,start,end)
                        res["after"][method_name] = method_code
                        res["method_names"].append(method_name)
    res["earlist_line"] = min(start_lines)
    return res

def get_global_vars(code,start_line):
    fields = {}
    trees = javalang.parse.parse(code)
    for _, node in javalang.parse.parse(code):
        func_intervals = set()
        if isinstance(
            node,
            (javalang.tree.FieldDeclaration),
        ):
            stat = get_string(code,node.start_position,node.end_position),
            node_name = node.declarators[0].name,
            # func_intervals.add(
            #     (
            #         node.start_position,
            #         node.end_position,
            #         stat,
            #         node
            #     )
            # )
            if node.start_position.line >= start_line:
                continue
            if node_name not in fields:
                fields[node_name[0]] = stat[0]
    return fields

def remove_comments(code):
    original_code = code
    new_code = code
    try:
        trees = javalang.parse.parse(code)
        if trees.package.documentation:
            package_comments = str(trees.package.documentation)
            new_code = code.replace(package_comments,"")
            code = new_code
    except:
        print("utils.py not found package documentation")

    new_code = code.replace(code.split("package ")[0],"")
    return new_code

def get_package(code):
    try:
        trees = javalang.parse.parse(code)
        if trees.package:
            print("***********package********")
            full_package = "package " + trees.package.name + ";"
            print(full_package)
            return full_package
    except:
        print("package not found")
        return None

def remove_imports(code):
    original_code = code
    new_code = code
    try:
        trees = javalang.parse.parse(code)
        if trees.imports:
            for import_node in trees.imports:
                import_stat = get_string(original_code,import_node.start_position,import_node.end_position)
                new_code = code.replace(import_stat,"")
                code = new_code
    except:
        return new_code
    return new_code

def read_imports(code):
    original_code = code
    imp_list = []
    try:
        trees = javalang.parse.parse(code)
        if trees.imports:
            for import_node in trees.imports:
                import_stat = get_string(original_code,import_node.start_position,import_node.end_position)
                imp_list.append(import_stat)
    except:
        return imp_list
    return imp_list

def get_test_method(test_name,class_content):
    method_list = parse_java_func_intervals(class_content)
    res = None
    for method_info in method_list:
        start, end, method_name, method_code, node = method_info[0:]
        if test_name == method_name:
            # if node.annotations != None:
            #     for ele in node.annotations:
            #         if ele.name == "Test":
            #             res = [start,end,method_name,method_code,node.annotations]
            # else: # no annotation
            res = [start,end,method_name,method_code,node.annotations]
    return res

def get_err_method(test_name,class_content,failure_lines):
    method_list = parse_java_func_intervals(class_content)
    res = None
    for method_info in method_list:
        start, end, method_name, method_code, node = method_info[0:]
        if test_name == method_name:
            for line in failure_lines:
                if int(line) >= start.line and int(line) <= end.line:
                    res = [start,end,method_name,method_code,node.annotations]
    return res

def get_string(data, start, end):
    if start is None:
        return ""

    end_pos = None

    if end is not None:
        end_pos = end.line #- 1

    lines = data.splitlines(True)
    string = "".join(lines[start.line:end_pos])
    string = lines[start.line - 1] + string

    if end is None:
        left = string.count("{")
        right = string.count("}")
        if right - left == 1:
            p = string.rfind("}")
            string = string[:p]

    return string


def parse_java_func_intervals(content: str) -> Set[Tuple[int, int]]:
    func_intervals = set()
    try:
        # trees = javalang.parse.parse(content)
        # print(trees)
        for _, node in javalang.parse.parse(content):
            # print("here")
            if isinstance(
                node,
                (javalang.tree.MethodDeclaration, javalang.tree.ConstructorDeclaration),
            ):
                func_intervals.add(
                    (
                        node.start_position,
                        node.end_position,
                        node.name,
                        get_string(content,node.start_position,node.end_position),
                        node
                    )
                )
        return func_intervals
    except Exception as e: # javalang.parser.JavaSyntaxError
        print("exp", e)
        return func_intervals

def read_java(f):
    fh = open(f, 'r', errors='ignore')
    data = fh.read()
    return data
    # parse_java_func_intervals(data,f)

def clean_code(code):
    code_no_comments = remove_comments(code)
    code_no_imports = remove_imports(code_no_comments)
    return code_no_imports

# trees = javalang.parse.parse(code_no_imports)
# print(trees)

# file = sys.argv[1]
# read_java(file)

def t(response):
    # regex = r"public\s+\w+\s+\w+\s*\([^)]*\)\s*(?:throws\s+\w+\s*)?\{(?:.|\n)*?\n\s*\}"
    # method_pattern = re.compile(regex, re.DOTALL)
    # matches = method_pattern.findall(code)
    
    # for match in matches:
    #     leftc = match.count("{")
    #     rightc = match.count("}")
    #     print(leftc,rightc)
    #     if leftc == rightc:
    #         print(match)

    code = response.replace("\n"," \n ")
    potential_match_final = ""
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
                        # print("done")
                elif "void" in potential_match_final:
                    tmpstr = potential_match_final.split("void ")[1]
                    k = tmpstr.rfind("}")
                    new_string = tmpstr[:k] + "\n"
                    final_match = "public void " + new_string
                    if final_match.count("{") == final_match.count("}"):
                        potential_match_final = final_match
    # print(potential_match_final)

def extract_java_code(text):
    lst = text.replace("```java","\n").replace("```","\n").replace("//<fix start>","\n").replace("//<fix end>","\n").split("\n")
    left = 0
    right = 0
    methods = {}
    idx = 0
    method = []
    inAmethod = False
    for line in lst:
        if "public class " in line:
            continue
        idx += 1
        l = line.count("{")
        left += l
        r = line.count("}")
        right += r
        if left == right and right > 0 and inAmethod == True:
            method.append(line)
            left = 0
            right = 0
            methods[str(idx)] = method
            method = []
            inAmethod = False
        elif left > right:
            inAmethod = True
            method.append(line)
        elif line.strip() in ["@Before","@After", "@BeforeEach","@AfterEach","@BeforeAll","@AfterAll","@BeforeClass","@AfterClass"]:
            inAmethod = True
            method.append(line)
    
    dummy_code = "public class Lambda {\n"
    for key in methods:
        method = "\n".join(methods[key]) + "\n"
        dummy_code += method
    dummy_code += "\n}\n"

    method_list = parse_java_func_intervals(dummy_code)
    print(method_list)
    if method_list != None:
        return method_list,True
    else:
        return methods,False

    # for key in methods:
    #     for line in methods[key]:
    #         print(line)
    #     if "()" in methods[key][0] and "{" in methods[key][0]:
    #         potential_method_name = (methods[key][0].split("()"))[0].split(" ")[-1]
    #         print(potential_method_name)
    #         key = potential_method_name

code = "package com.adobe.cq.wcm.core.components.internal.models.v2;\nimport java.text.ParseException;"
# get_package(code)
code2 = "Here is the fixed code:\n\n```java\n//<fix start> public class a() {\n\nimport java.util.LinkedHashSet;\nimport java.util.LinkedHashMap;\n\npublic void nextRecord_fairProcessing() {\n    TopicPartition topic1Partition1 = new TopicPartition(\"topic1\", 1);\n    TopicPartition topic1Partition2 = new TopicPartition(\"topic1\", 2);\n    TopicPartition topic2Partition1 = new TopicPartition(\"topic2\", 1);\n    TopicPartition topic2Partition2 = new TopicPartition(\"topic2\", 2);\n\n    when(consumer.committed(topic1Partition1)).thenReturn(new OffsetAndMetadata(0L));\n    when(consumer.committed(topic1Partition2)).thenReturn(new OffsetAndMetadata(0L));\n    when(consumer.committed(topic2Partition1)).thenReturn(new OffsetAndMetadata(0L));\n    when(consumer.committed(topic2Partition2)).thenReturn(new OffsetAndMetadata(0L));\n\n    List<TopicPartition> topicPartitions = Arrays.asList(topic1Partition1, topic1Partition2, topic2Partition1,\n            topic2Partition2);\n\n    Map<TopicPartition, List<ConsumerRecord<String, String>>> recordsMap = new LinkedHashMap<>();\n\n    // Provide 3 records per partition\n    topicPartitions.forEach(tp -> {\n        List<ConsumerRecord<String, String>> records = new ArrayList<>();\n        for(int message=0; message<3; message++) {\n            records.add(new ConsumerRecord<>(tp.topic(), tp.partition(), message, \"key\", tp.toString() + \" Message: \" + message));\n        }\n        recordsMap.put(tp, records);\n    });\n\n    // Setup consumer to read these records\n    ConsumerRecords<String, String> records = new ConsumerRecords<>(recordsMap);\n    when(consumer.poll(any(Duration.class))).thenReturn(records);\n\n    rebuildConsumer();\n    processingConsumer.rebalanceListener.onPartitionsAssigned(topicPartitions);\n\n    // We are asserting that we will read message 0 for each partition before reading 1 and then 2\n    for(int message = 0; message < 3; message++) {\n\n        // Handle any partition ordering\n        final int messageInt = message;\n        Collection<String> values = topicPartitions.stream().map(tp -> tp.toString() + \" Message: \" + messageInt)\n                .collect(Collectors.toCollection(LinkedHashSet::new));\n\n        for(int partition = 0; partition < topicPartitions.size(); partition++) {\n            String value = nextRecordIsPresent().value();\n            assertThat(\"Expected to remove [\" + value + \"] but it was not part of values [\" + values + \"]\",\n                    values.remove(value), is(true));\n        }\n\n        assertThat(values, empty());\n    }\n\n    // We should have read all records\n    Optional<ConsumerRecord<String, String>> optional = processingConsumer.nextRecord(POLL_TIME);\n    assertThat(\"expected optional consumer record to not be present\", optional.isPresent(), is(false));\n}\n}\n//<fix end>\n```"

# data = read_java("t.txt")
# extract_java_code(data)
# t(code2)