import { useCallback, useEffect, useRef } from "react";
import { ScrollView, StyleSheet, Text, View, type ScrollViewInstance } from "react-native";

import type { IsoDate, MonthRecord } from "../../domain/models";
import { getMobileTheme } from "../../theme";
import { monthTitle } from "../overview/overviewFormat";
import { CalendarMonthGrid } from "./CalendarMonthGrid";
import { MonthActions } from "./MonthActions";

const theme = getMobileTheme("dark");
export type CalendarJump = { date: IsoDate; request: number };

type Props = {
  months: MonthRecord[];
  today: IsoDate;
  jump: CalendarJump | null;
  loading: boolean;
  onDayPress(date: IsoDate): void;
};

export function CalendarYearView({ months, today, jump, loading, onDayPress }: Props) {
  const scroll = useRef<ScrollViewInstance>(null);
  const pending = useRef<CalendarJump | null>(null);
  const consumedRequest = useRef<number | null>(null);
  const frames = useRef(new Map<number, { y?: number; height?: number; gridY?: number }>());
  const todayRow = useRef<{ date: IsoDate; y: number; height: number } | null>(null);
  const viewport = useRef(0);
  const contentHeight = useRef(0);

  const scrollToToday = useCallback(() => {
    const target = pending.current;
    if (!target || loading || !viewport.current || !contentHeight.current) return;
    const month = months.find((item) => target.date.startsWith(`${item.year}-${String(item.month).padStart(2, "0")}-`));
    const frame = month && frames.current.get(month.month);
    const row = todayRow.current;
    if (!frame || frame.y === undefined || frame.height === undefined || frame.gridY === undefined || row?.date !== target.date) return;
    const y = frame.height <= viewport.current ? frame.y
      : frame.y + frame.gridY + row.y - (viewport.current - row.height) / 2;
    scroll.current?.scrollTo({ y: Math.max(0, Math.min(y, contentHeight.current - viewport.current)), animated: true });
    pending.current = null;
    consumedRequest.current = target.request;
  }, [loading, months]);

  useEffect(() => {
    if (!jump) pending.current = null;
    else if (consumedRequest.current !== jump.request) pending.current = jump;
    const frame = requestAnimationFrame(scrollToToday);
    return () => cancelAnimationFrame(frame);
  }, [jump, scrollToToday]);

  return (
    <ScrollView
      ref={scroll}
      style={styles.list}
      contentContainerStyle={styles.content}
      onLayout={(event) => { viewport.current = event.nativeEvent.layout.height; scrollToToday(); }}
      onContentSizeChange={(_width, height) => { contentHeight.current = height; scrollToToday(); }}
    >
      {months.map((month) => (
        <View key={month.month} style={styles.month} onLayout={(event) => {
          frames.current.set(month.month, { ...frames.current.get(month.month), ...event.nativeEvent.layout });
          scrollToToday();
        }}>
          <Text accessibilityRole="header" style={styles.title}>{monthTitle(month.year, month.month)}</Text>
          <View onLayout={(event) => {
            const frame = frames.current.get(month.month);
            if (frame) frames.current.set(month.month, { ...frame, gridY: event.nativeEvent.layout.y });
            else frames.current.set(month.month, { gridY: event.nativeEvent.layout.y });
            scrollToToday();
          }}>
            <CalendarMonthGrid month={month} today={today} onDayPress={onDayPress} onTodayLayout={(y, height) => {
              todayRow.current = { date: today, y, height };
              scrollToToday();
            }} />
          </View>
          <MonthActions month={month} today={today} disabled={loading} />
        </View>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  list: { flex: 1 },
  content: { padding: theme.spacing.lg, paddingBottom: theme.spacing.xl * 4, gap: theme.spacing.xl },
  month: { gap: theme.spacing.md },
  title: { color: theme.colors.text, fontSize: 18, fontWeight: "800" },
});
