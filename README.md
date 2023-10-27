# FlakyDoctor


## PRs

We opened 19 PRs for 60 tests (one PR may include fixes for multiple tests):

**Accepted PRs:**
- https://github.com/funkygao/cp-ddd-framework/pull/65
- https://github.com/perwendel/spark/pull/1285
- https://github.com/apache/pinot/pull/11771
- https://github.com/dropwizard/dropwizard/pull/7629
- https://github.com/opengoofy/hippo4j/pull/1495
- https://github.com/moquette-io/moquette/pull/781

**Opened PRs:**
- https://github.com/dyc87112/SpringBoot-Learning/pull/98
- https://github.com/graphhopper/graphhopper/pull/2899
- https://github.com/BroadleafCommerce/BroadleafCommerce/pull/2901
- https://github.com/dianping/cat/pull/2320
- https://github.com/hellokaton/30-seconds-of-java8/pull/8
- https://github.com/AmadeusITGroup/workflow-cps-global-lib-http-plugin/pull/68
- https://github.com/wro4j/wro4j/pull/1167
- https://github.com/jnr/jnr-posix/pull/185
- https://github.com/kevinsawicki/http-request/pull/177
- https://github.com/yangfuhai/jboot/pull/117
- https://github.com/FasterXML/jackson-jakarta-rs-providers/pull/22

*We are waiting for developers to approve our requests to create an issue for the following PRs:*
- https://github.com/dserfe/flink/pull/1
- https://github.com/dserfe/nifi/pull/1
- https://github.com/dserfe/jenkins/pull/1

**Why other tests can not be opened PRs:**
```
Tests are deleted in the latest version of the project:
- org.apache.dubbo.registry.client.metadata.ServiceInstanceMetadataUtilsTest.testMetadataServiceURLParameters
- org.apache.cayenne.CayenneContextClientChannelEventsIT.testSyncToOneRelationship
- org.apache.shardingsphere.elasticjob.cloud.scheduler.env.BootstrapEnvironmentTest.assertWithoutEventTraceRdbConfiguration
- org.apache.shardingsphere.elasticjob.cloud.scheduler.mesos.AppConstraintEvaluatorTest.assertExistExecutorOnS0
- net.sf.marineapi.ais.event.AbstractAISMessageListenerTest.testParametrizedConstructor
- net.sf.marineapi.ais.event.AbstractAISMessageListenerTest.testSequenceListener
- com.willwinder.universalgcodesender.GrblControllerTest.testGetGrblVersion
- com.willwinder.universalgcodesender.GrblControllerTest.testIsReadyToStreamFile

Tests are fixed by developers in the latest version of the project:
- io.elasticjob.lite.lifecycle.internal.settings.JobSettingsAPIImplTest.assertUpdateJobSettings
- net.sf.marineapi.ais.event.AbstractAISMessageListenerTest.testBasicListenerWithUnexpectedMessage
- net.sf.marineapi.ais.event.AbstractAISMessageListenerTest.testConstructor
- net.sf.marineapi.ais.event.AbstractAISMessageListenerTest.testGenericsListener
- net.sf.marineapi.ais.event.AbstractAISMessageListenerTest.testOnMessageWithExpectedMessage
- com.willwinder.universalgcodesender.GrblControllerTest.rawResponseHandlerOnErrorWithNoSentCommandsShouldSendMessageToConsole
- com.willwinder.universalgcodesender.GrblControllerTest.rawResponseHandlerWithKnownErrorShouldWriteMessageToConsole
- com.willwinder.universalgcodesender.GrblControllerTest.rawResponseHandlerWithUnknownErrorShouldWriteGenericMessageToConsole
- com.graphhopper.isochrone.algorithm.IsochroneTest.testSearch

Tests are actually different types of flakiness after inspected:
- com.baidu.jprotobuf.pbrpc.EchoServiceTest.testDynamiceTalkTimeout

Repository is archived:
- io.searchbox.indices.RolloverTest.testBasicUriGeneration
- com.netflix.exhibitor.core.config.zookeeper.TestZookeeperConfigProvider.testConcurrentModification
- org.springframework.security.oauth2.provider.client.JdbcClientDetailsServiceTests.testUpdateClientRedirectURI
``` 

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
