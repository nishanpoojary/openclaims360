import { Stack, StackProps } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as s3 from 'aws-cdk-lib/aws-s3';

export class BucketsStack extends Stack {
    constructor(scope: Construct, id: string, props?: StackProps) {
        super(scope, id, props);

        // one test bucket so the stack is valid
        new s3.Bucket(this, 'TestBucket', {
            versioned: true,
            encryption: s3.BucketEncryption.S3_MANAGED,
        });
    }
}
