clone_dir=$1
api_key=$2
model=$3
dir_name=$$4
flakies=$5
nondex_times=5

TimeStamp=$(echo -n $(date "+%Y-%m-%d %H:%M:%S") | shasum | cut -f 1 -d " ")

mkdir -p ${dir_name}
DIR=${dir_name}/ID_Results_${model}_${clone_dir}_${TimeStamp}
mkdir -p ${DIR}


exec 3>&1 4>&2
trap $(exec 2>&4 1>&3) 0 1 2 3
exec 1>${DIR}/${TimeStamp}.log 2>&1

echo "* "STARTING at $(date) 
echo "* "REPO VERSION $(git rev-parse HEAD)
# flakies=( od_brit.csv )
for f in "${flakies[@]}"; do
    SubTimeStamp=$(echo -n $(date "+%Y-%m-%d %H:%M:%S") | shasum | cut -f 1 -d " ")
    result_csv=${DIR}/${model}_results_${SubTimeStamp}.csv
    result_json=${DIR}/${model}_results_${SubTimeStamp}.json
    save_dir=${DIR}
    unfixed_csv=${DIR}/unfixed_${SubTimeStamp}.csv
    test_file_info=${DIR}/${model}_test_final_result_${SubTimeStamp}.json
    python3 -u src/repair_brit.py ${f} ${clone_dir} ${api_key} ${result_csv} ${result_json} ${save_dir} ${unfixed_csv} ${model} ${test_file_info} ${nondex_times}
done

echo "* "ENDING at $(date)