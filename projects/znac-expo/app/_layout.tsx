import { DarkTheme, ThemeProvider } from "expo-router/react-navigation";
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useEffect, useState } from "react";
import "react-native-reanimated";

import { initializeDatabase } from "../src/db";
import { useMonthStore } from "../src/stores/monthStore";
import { useSettingsStore } from "../src/stores/settingsStore";

export const unstable_settings = {
  anchor: "(tabs)",
};

export default function RootLayout() {
  const loadMonth = useMonthStore((state) => state.load);
  const loadSettings = useSettingsStore((state) => state.load);
  const [databaseReady, setDatabaseReady] = useState(false);

  useEffect(() => {
    initializeDatabase().then(() => {
      setDatabaseReady(true);
    });
  }, []);

  useEffect(() => {
    if (!databaseReady) {
      return;
    }

    loadSettings();
    loadMonth();
  }, [databaseReady, loadSettings, loadMonth]);

  if (!databaseReady) {
    return null;
  }

  return (
    <ThemeProvider value={DarkTheme}>
      <Stack>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />

        <Stack.Screen
          name="day/[date]"
          options={{
            title: "Day details",
          }}
        />

        <Stack.Screen
          name="modals/break-editor"
          options={{
            presentation: "modal",
            title: "Interruptions",
          }}
        />

        <Stack.Screen
          name="modals/delete-day"
          options={{
            presentation: "modal",
            title: "Delete day",
          }}
        />
      </Stack>

      <StatusBar style="light" />
    </ThemeProvider>
  );
}
