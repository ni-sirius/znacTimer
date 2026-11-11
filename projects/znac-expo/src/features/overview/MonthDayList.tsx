import { ArrowDown, ArrowUp } from "lucide-react-native";
import { useCallback, useEffect, useRef, useState } from "react";
import { Animated, Pressable, ScrollView, StyleSheet, Text, View, type ScrollViewInstance } from "react-native";

import type { DayRecord } from "../../domain/models";
import { DayRow } from "../day/DayRow";
import { getMobileTheme } from "../../theme";

const theme = getMobileTheme("dark");

type MonthDayListProps = {
  days: DayRecord[];
  today: string;
  bottomInset: number;
  onDayPress: (date: string) => void;
};

export function MonthDayList({ days, today, bottomInset, onDayPress }: MonthDayListProps) {
  const scrollRef = useRef<ScrollViewInstance>(null);
  const scrollOffset = useRef(0);
  const hasAutoScrolled = useRef(false);
  const [opacity] = useState(() => new Animated.Value(0));
  const [todayFrame, setTodayFrame] = useState<{ y: number; height: number } | null>(null);
  const [viewportHeight, setViewportHeight] = useState(0);
  const [contentHeight, setContentHeight] = useState(0);
  const [shortcut, setShortcut] = useState<{ direction: "up" | "down"; visible: boolean }>({ direction: "down", visible: false });

  const updateDirection = useCallback(() => {
    const visibleHeight = viewportHeight - bottomInset;
    let next: "up" | "down" | null = null;
    if (todayFrame && visibleHeight > 0) {
      if (todayFrame.y + todayFrame.height <= scrollOffset.current) next = "up";
      else if (todayFrame.y >= scrollOffset.current + visibleHeight) next = "down";
    }
    setShortcut((previous) => {
      const direction = next ?? previous.direction;
      const visible = next !== null;
      return previous.direction === direction && previous.visible === visible
        ? previous
        : { direction, visible };
    });
  }, [todayFrame, viewportHeight, bottomInset]);

  const scrollToToday = useCallback(() => {
    if (!todayFrame) return;
    scrollRef.current?.scrollTo({
      y: Math.max(0, todayFrame.y - (viewportHeight - bottomInset - todayFrame.height) / 2),
      animated: true,
    });
  }, [todayFrame, viewportHeight, bottomInset]);

  useEffect(() => {
    const frame = requestAnimationFrame(updateDirection);
    return () => cancelAnimationFrame(frame);
  }, [updateDirection]);
  useEffect(() => {
    if (!hasAutoScrolled.current && todayFrame && viewportHeight > bottomInset && bottomInset > 0 && contentHeight > 0) {
      hasAutoScrolled.current = true;
      scrollToToday();
    }
  }, [todayFrame, viewportHeight, bottomInset, contentHeight, scrollToToday]);
  useEffect(() => {
    const animation = Animated.timing(opacity, {
      toValue: shortcut.visible ? 1 : 0,
      duration: 180,
      useNativeDriver: true,
    });
    animation.start();
    return () => animation.stop();
  }, [shortcut.visible, opacity]);

  const Arrow = shortcut.direction === "up" ? ArrowUp : ArrowDown;

  return (
    <View style={styles.container}>
      {/* At most 31 rows: measure real layouts instead of estimating card heights. */}
      <ScrollView
        ref={scrollRef}
        contentInsetAdjustmentBehavior="never"
        automaticallyAdjustContentInsets={false}
        contentContainerStyle={[styles.list, { paddingBottom: bottomInset + theme.spacing.md }]}
        onLayout={(event) => setViewportHeight(event.nativeEvent.layout.height)}
        onContentSizeChange={(_, height) => setContentHeight(height)}
        onScroll={(event) => {
          scrollOffset.current = event.nativeEvent.contentOffset.y;
          updateDirection();
        }}
        scrollEventThrottle={16}
        showsVerticalScrollIndicator={false}
      >
        {days.map((day) => (
          <View
            key={day.workDate}
            onLayout={day.workDate === today
              ? (event) => {
                  const { y, height } = event.nativeEvent.layout;
                  setTodayFrame({ y, height });
                }
              : undefined}
          >
            <DayRow day={day} isToday={day.workDate === today} onPress={onDayPress} />
          </View>
        ))}
      </ScrollView>
      <Animated.View
        pointerEvents={shortcut.visible ? "auto" : "none"}
        accessibilityElementsHidden={!shortcut.visible}
        importantForAccessibility={shortcut.visible ? "auto" : "no-hide-descendants"}
        style={[styles.todayShortcut, { bottom: bottomInset + theme.spacing.sm, opacity }]}
      >
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`Scroll ${shortcut.direction} to today`}
          onPress={scrollToToday}
          style={styles.todayButton}
        >
          <Arrow size={20} color={theme.colors.onPrimary} />
          <Text style={styles.todayText}>Today</Text>
        </Pressable>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  list: {
    gap: theme.spacing.md,
    paddingTop: theme.spacing.sm,
    paddingHorizontal: theme.spacing.lg,
  },
  todayShortcut: {
    position: "absolute",
    right: theme.spacing.lg,
  },
  todayButton: {
    minHeight: 44,
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.xs,
    paddingHorizontal: theme.spacing.md,
    borderRadius: theme.radius.pill,
    backgroundColor: theme.colors.primary,
  },
  todayText: {
    color: theme.colors.onPrimary,
    fontWeight: "700",
  },
});
