import { CrudModule } from "@/components/CrudModule";
import { expenseConfig } from "@/lib/configs";
import { ExpenseLedger } from "@/components/ExpenseLedger";
import { PageHeader } from "@/pages/ModulePages";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export default function Expenses() {
  return (
    <div data-testid="expenses-page">
      <PageHeader title="Expense Management" subtitle="Unified ledger across all modules plus manual expense entries" />
      <Tabs defaultValue="ledger">
        <TabsList className="rounded-none border border-slate-200 bg-white p-0">
          <TabsTrigger value="ledger" data-testid="expenses-tab-ledger" className="rounded-none px-5 py-2.5 data-[state=active]:bg-slate-900 data-[state=active]:text-white">Full Ledger</TabsTrigger>
          <TabsTrigger value="manual" data-testid="expenses-tab-manual" className="rounded-none px-5 py-2.5 data-[state=active]:bg-slate-900 data-[state=active]:text-white">Manual Entries</TabsTrigger>
        </TabsList>
        <TabsContent value="ledger" className="mt-5"><ExpenseLedger /></TabsContent>
        <TabsContent value="manual" className="mt-5"><CrudModule {...expenseConfig} /></TabsContent>
      </Tabs>
    </div>
  );
}
