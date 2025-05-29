#!/usr/bin/env node
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
require("source-map-support/register");
const aws_cdk_lib_1 = require("aws-cdk-lib");
const buckets_stack_1 = require("../lib/buckets-stack");
const generator_stack_1 = require("../lib/generator-stack");
const budget_stack_1 = require("../lib/budget-stack");
const stream_box_stack_1 = require("../lib/stream-box-stack");
const fraud_api_stack_1 = require("../lib/fraud-api-stack");
const app = new aws_cdk_lib_1.App();
new buckets_stack_1.BucketsStack(app, 'BucketsStack');
new generator_stack_1.GeneratorStack(app, 'GeneratorStack');
new budget_stack_1.BudgetStack(app, 'BudgetStack');
new stream_box_stack_1.StreamBoxStack(app, 'StreamBoxStack');
new fraud_api_stack_1.FraudApiStack(app, 'FraudApiStack');
