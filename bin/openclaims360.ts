#!/usr/bin/env node
import 'source-map-support/register';
import { App } from 'aws-cdk-lib';

import { BucketsStack } from '../lib/buckets-stack';
import { GeneratorStack } from '../lib/generator-stack';
import { BudgetStack } from '../lib/budget-stack';
import { StreamBoxStack } from '../lib/stream-box-stack';
import { FraudApiStack } from '../lib/fraud-api-stack';

const app = new App();

new BucketsStack(app, 'BucketsStack');
new GeneratorStack(app, 'GeneratorStack');
new BudgetStack(app, 'BudgetStack');
new StreamBoxStack(app, 'StreamBoxStack');
new FraudApiStack(app, 'FraudApiStack');
