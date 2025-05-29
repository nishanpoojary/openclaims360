import { Stack, StackProps } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as budgets from 'aws-cdk-lib/aws-budgets';

export class BudgetStack extends Stack {
    constructor(scope: Construct, id: string, props?: StackProps) {
        super(scope, id, props);

        new budgets.CfnBudget(this, 'ZeroDollarGuard', {
            budget: {
                budgetName: 'OpenClaimsFreeGuard',
                budgetType: 'COST',
                timeUnit: 'MONTHLY',
                budgetLimit: { amount: 0.01, unit: 'USD' },
            },
            notificationsWithSubscribers: []
        });
    }
}
