import type { TaskEvent } from "../domain/types";
import { Card, CardContent } from "./primitives/Card";

interface ActivityStreamProps {
  events: TaskEvent[];
}

export function ActivityStream({ events }: ActivityStreamProps) {
  return (
    <Card
      className="pointer-events-none absolute bottom-[180px] left-ui-xs z-20 h-40 w-[min(560px,calc(100%_-_16px))] border-none bg-transparent py-ui-xs @3xl/main:bottom-[164px] @3xl/main:h-52"
      size="none"
    >
      <CardContent className="flex h-full flex-col justify-end gap-ui-xxs overflow-hidden">
        {events.slice(0, 5).map((event) => (
          <article className="flex max-w-max items-center gap-1" key={event.id}>
            <div className="h-px w-4 bg-terminal" />
            <div className="bg-background/45 px-2 py-1 text-[10px] font-extrabold uppercase text-foreground shadow-long [&_span]:bg-white [&_span]:px-1 [&_span]:py-px [&_span]:text-black">
              <span>{event.state}</span> {event.message}
            </div>
            <div className="hidden bg-fuel/20 px-2 py-0.5 text-[10px] font-semibold uppercase text-fuel @md/main:block">
              {event.agent} / {event.at}
            </div>
          </article>
        ))}
      </CardContent>
    </Card>
  );
}
