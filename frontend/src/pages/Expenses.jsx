import { useState } from "react";
import { CrudModule } from "@/components/CrudModule";
import { expenseConfig } from "@/lib/configs";
import { ExpenseLedger } from "@/components/ExpenseLedger";
import { ExpenseOverview, ExpenseInsights } from "@/components/ExpenseIntel";
import { BudgetPanel } from "@/components/BudgetPanel";
import { PageHeader } from "@/pages/ModulePages";
import { PeriodFilter } from "@/components/PeriodFilter";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const tabCls = "rounded-none px-5 py-2.5 data-[state=active]:bg-slate-900 data-[state=active]:text-white";

export default function Expenses() {
  const [range, setRange] = useState({});
  const filters = {};
  if (range.start_date) filters.start_date = range.start_date;
  if (range.end_date) filters.end_date = range.end_date;

  return (
    <div data-testid="expenses-page">
      <PageHeader title="Expense Intelligence" subtitle="Consolidated ledger, budgets, insights and cost control across every module" />
      <PeriodFilter testIdPrefix="expenses-period" onChange={setRange} />
      <Tabs defaultValue="overview">
        <TabsList className="h-auto flex-wrap rounded-none border border-slate-200 bg-white p-0">
          <TabsTrigger value="overview" data-testid="expenses-tab-overview" className={tabCls}>Overview</TabsTrigger>
          <TabsTrigger value="ledger" data-testid="expenses-tab-ledger" className={tabCls}>Full Ledger</TabsTrigger>
          <TabsTrigger value="manual" data-testid="expenses-tab-manual" className={tabCls}>Manual Entries</TabsTrigger>
          <TabsTrigger value="budgets" data-testid="expenses-tab-budgets" className={tabCls}>Budget vs Actual</TabsTrigger>
          <TabsTrigger value="insights" data-testid="expenses-tab-insights" className={tabCls}>Insights</TabsTrigger>
        </TabsList>
        <TabsContent value="overview" className="mt-5">
          <ExpenseOverview startDate={range.start_date} endDate={range.end_date} />
        </TabsContent>
        <TabsContent value="ledger" className="mt-5">
          <ExpenseLedger startDate={range.start_date} endDate={range.end_date} />
        </TabsContent>
        <TabsContent value="manual" className="mt-5">
          <CrudModule {...expenseConfig} fixedFilters={filters} />
        </TabsContent>
        <TabsContent value="budgets" className="mt-5">
          <BudgetPanel />
        </TabsContent>
        <TabsContent value="insights" className="mt-5">
          <ExpenseInsights />
        </TabsContent>
      </Tabs>
    </div>
  );
}
