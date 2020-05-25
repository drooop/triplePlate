import taskflow.engines
from taskflow.patterns import linear_flow as linearflow
from taskflow import task, retry

class EchoTask(task.Task):
    def execute(self, *args, **kwargs):
        print(self.name)
        print(args)
        print(kwargs)


if __name__ == '__main__':
    flow = linearflow.Flow('f1').add(
        EchoTask('t1'),
        linearflow.Flow('f2', retry=retry.ForEach(values=['a', 'b', 'c'], name='r1', provides='value')).add(
            EchoTask('t2'),
            EchoTask('t3', requires='value')),
        EchoTask('t4'))
    
    # while True:
    engine = taskflow.engines.load(flow, store=dict())
    engine.run()
