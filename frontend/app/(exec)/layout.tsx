import { AppShell } from "@/components/app-shell";

export default function ExecLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
