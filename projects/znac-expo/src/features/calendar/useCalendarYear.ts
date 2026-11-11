import { useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";

import { createRepository, getDatabase } from "../../db";
import type { MonthRecord } from "../../domain/models";
import { useMonthStore } from "../../stores/monthStore";
import { storeErrorMessage } from "../../stores/storeErrors";

export function useCalendarYear(year: number) {
  const changes = useMonthStore((state) => state.monthsByPeriod);
  const [months, setMonths] = useState<MonthRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useFocusEffect(useCallback(() => {
    let active = true;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const result = await createRepository(await getDatabase()).readCalendarYear(year);
        if (active && changes === useMonthStore.getState().monthsByPeriod) setMonths(result);
      } catch (error) {
        if (active) setError(storeErrorMessage(error));
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
  }, [year, changes]));

  return { months: months[0]?.year === year ? months : [], loading, error };
}
