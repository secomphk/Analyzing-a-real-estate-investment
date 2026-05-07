import type { LucideIcon } from "lucide-react";
import { Inbox } from "lucide-react";

interface Props {
  title: string;
  detail?: string;
  Icon?: LucideIcon;
  action?: React.ReactNode;
}

export function EmptyState({ title, detail, Icon = Inbox, action }: Props) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-slate-200 bg-white px-6 py-12 text-center">
      <Icon className="h-10 w-10 text-slate-400" />
      <h3 className="text-sm font-semibold text-slate-700">{title}</h3>
      {detail && <p className="max-w-md text-sm text-slate-500">{detail}</p>}
      {action}
    </div>
  );
}
