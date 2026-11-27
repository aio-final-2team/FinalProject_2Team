import { useEffect, useState } from "react";
import { useSaveNotificationSettings, useNotificationSettings } from "@/api/staff";
import { Button } from "@/components/Button";
import { QueryState } from "@/components/QueryState";
import { ScreenTop } from "@/components/ScreenTop";
import { useToast } from "@/components/Toast";

const field = "h-12 w-full rounded-md border-[1.5px] border-line bg-card px-3 text-body outline-none focus:border-accent focus:shadow-[0_0_0_3px_var(--tint)]";

/** 알림 조용한 시간. 이 시간에 온 알림은 끝나는 시간으로 미뤄 받는다. 두 칸 모두 비우면 기본 시간을 따른다 */
export function NotifySettingsPage() {
  const q = useNotificationSettings();
  const save = useSaveNotificationSettings();
  const toast = useToast();
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  useEffect(() => {
    if (q.data) {
      setStart(q.data.quiet_start ?? "");
      setEnd(q.data.quiet_end ?? "");
    }
  }, [q.data]);

  const bothOrNone = (!start && !end) || (!!start && !!end);
  const same = !!start && start === end;
  const unchanged = (q.data?.quiet_start ?? "") === start && (q.data?.quiet_end ?? "") === end;
  const invalid = !bothOrNone || same;

  const submit = () =>
    save.mutate(
      { quiet_start: start || null, quiet_end: end || null },
      {
        onSuccess: () => toast({ kind: "ok", title: "저장했어요" }),
        onError: () => toast({ kind: "error", title: "저장하지 못했어요", sub: "연결을 확인하고 다시 눌러 주세요" }),
      },
    );

  return (
    <div className="mx-auto max-w-[680px] px-4 pb-10">
      <ScreenTop back={{ to: "/teacher/notifications", label: "알림" }} title="알림 조용한 시간" sub="이 시간에 온 알림은 끝나는 시간에 알려 드려요" />
      <QueryState queries={[q]} skeleton={2} errorTitle="설정을 불러오지 못했어요">
        <section className="mt-5 grid gap-3 rounded-lg bg-card p-4 shadow-card" aria-label="조용한 시간">
          <div className="grid grid-cols-2 gap-3">
            <label className="grid gap-1.5">
              <span className="px-1 text-footnote font-semibold text-ink2">시작</span>
              <input type="time" value={start} onChange={(e) => setStart(e.target.value)} className={field} />
            </label>
            <label className="grid gap-1.5">
              <span className="px-1 text-footnote font-semibold text-ink2">끝</span>
              <input type="time" value={end} onChange={(e) => setEnd(e.target.value)} className={field} />
            </label>
          </div>
          <p className="px-1 text-caption text-ink2">밤을 넘겨도 돼요. 예를 들어 22:00부터 07:00까지로 정할 수 있어요. 긴급한 알림은 시간과 관계없이 바로 와요.</p>
          {!bothOrNone && <p role="alert" className="px-1 text-caption text-danger">시작과 끝을 모두 정해 주세요</p>}
          {same && <p role="alert" className="px-1 text-caption text-danger">시작과 끝이 같을 수 없어요</p>}
          <div className="flex gap-2">
            <Button variant="gray" disabled={!start && !end} onClick={() => { setStart(""); setEnd(""); }} className="flex-1">비우기</Button>
            <Button loading={save.isPending} disabled={invalid || unchanged} onClick={submit} className="flex-1">저장</Button>
          </div>
          {!q.data?.quiet_start && !start && <p className="px-1 text-caption text-ink2">정해 둔 시간이 없어요. 기본 알림 시간을 따라요.</p>}
        </section>
      </QueryState>
    </div>
  );
}
