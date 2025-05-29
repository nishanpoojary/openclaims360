import { Stack, StackProps, Duration } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';

export class GeneratorStack extends Stack {
    constructor(scope: Construct, id: string, props?: StackProps) {
        super(scope, id, props);

        // tiny placeholder Lambda – we'll package the real Python later
        const fn = new lambda.Function(this, 'GenFn', {
            runtime: lambda.Runtime.NODEJS_18_X,
            handler: 'index.handler',
            code: lambda.Code.fromInline(`exports.handler = async () => { console.log("tick"); };`)
        });

        // run every minute
        new events.Rule(this, 'Schedule', {
            schedule: events.Schedule.rate(Duration.minutes(1)),
            targets: [new targets.LambdaFunction(fn)],
        });
    }
}
