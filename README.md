# FlakyDoctor


## PRs (Full list to be added)

- https://github.com/funkygao/cp-ddd-framework/pull/65
- https://github.com/perwendel/spark/pull/1285
- https://github.com/dyc87112/SpringBoot-Learning/pull/98
- https://github.com/apache/pinot/pull/11771
- https://github.com/moquette-io/moquette/pull/781
- https://github.com/BroadleafCommerce/BroadleafCommerce/pull/2901
- https://github.com/graphhopper/graphhopper/pull/2887
- https://github.com/dropwizard/dropwizard/pull/7629

## Reproduce results

To set up the environments by:
```
bash -x scripts/setup.sh
```

To reproduce the results, one can run commands:
```
bash -x scripts/all.sh inputCsv cloneDir apiKey resDir fixScript
```
The arguments are as follows:
```
- inputCsv: An input csv files which includes the info of `project,sha,module,test,type,status,pr,notes` for each test, such as `https://github.com/apache/nifi,2bd752d868a8f3e36113b078bb576cf054e945e8,nifi-commons/nifi-record,org.apache.nifi.serialization.record.TestDataTypeUtils.testInferTypeWithMapNonStringKeys,ID,,,,`
- cloneDir: the directory where all Java projects are located
- apiKey: OpenAI token
- resDir: the directory to save all results. Each run of the experiments will generate a directory with a unique SHA as the folder name, under the folder there are patches, detailed result information, and all logs
- fixScript: specify one of the following scripts: `ID_flakiness.py`, `OD_flakiness.py`, `NOD_flakiness.py`
```