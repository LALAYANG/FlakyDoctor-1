INPUT_CSV=$1 #project_url
CLONE_DIR=$2 # dir to clone all projects
OUTPUT_DIR=$3 # dir to save outputs/logs

TimeStamp=$(echo -n $(date "+%Y-%m-%d %H:%M:%S") | shasum | cut -f 1 -d " ")

mkdir -p ${CLONE_DIR}
mkdir -p ./${OUTPUT_DIR}/${TimeStamp}/logs

PWD_DIR=$(pwd)
MAIN_DIR=$(pwd)/${CLONE_DIR}
LOG_DIR=$(pwd)/${OUTPUT_DIR}/${TimeStamp}/logs

exec 3>&1 4>&2
trap $(exec 2>&4 1>&3) 0 1 2 3
exec 1>${LOG_DIR}/${TimeStamp}.log 2>&1

echo "* "STARTING at $(date) 
echo "* "REPO VERSION $(git rev-parse HEAD)

if [[ ! -f ${INPUT_CSV} ]]; then
    echo ${INPUT_CSV} does not exist in ${PWD_DIR}
    exit
fi

for info in $(cat $INPUT_CSV); do
    URL=$(echo ${info} | cut -d, -f1)
    SHA=$(echo ${info} | cut -d, -f2)
    url=${URL/$'\r'/}
    sha=${SHA/$'\r'/}
    project=${url##*/}

    echo ${url} ${sha}

    cd ${MAIN_DIR}

    if [[ ! -d ${sha} ]]; then
        echo Directory ${sha} does not exist in ${MAIN_DIR}
        mkdir -p ${sha}
        cd ${sha}
        git clone ${url}
        cd ${project}
        git checkout ${sha}
    else
        echo Directory ${sha} exists in ${MAIN_DIR}
        cd ${sha}
        if [[ ! -d ${project} ]]; then
            git clone ${url}
        fi
        cd ${project}
        git stash
        git checkout ${sha}
    fi
    
    done

cd ${PWD_DIR}
echo "* "ENDING at $(date)