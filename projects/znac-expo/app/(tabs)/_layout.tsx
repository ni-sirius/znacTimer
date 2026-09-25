import MaterialIcons from "@expo/vector-icons/MaterialIcons";
import { Tabs } from "expo-router";
import { NativeTabs } from "expo-router/unstable-native-tabs";
import type { ComponentProps } from "react";
import { Platform } from "react-native";

import { MAIN_TABS } from "../../src/navigation/tabs";

type MaterialIconName = ComponentProps<typeof MaterialIcons>["name"];

export default function TabLayout() {
  if (Platform.OS === "ios") {
    return <IosNativeTabs />;
  }

  return <AndroidTabs />;
}

function IosNativeTabs() {
  return (
    <NativeTabs>
      {MAIN_TABS.map((tab) => (
        <NativeTabs.Trigger key={tab.name} name={tab.name}>
          <NativeTabs.Trigger.Icon
            sf={{
              default: tab.iosIcon.default,
              selected: tab.iosIcon.selected,
            }}
          />
          <NativeTabs.Trigger.Label>{tab.title}</NativeTabs.Trigger.Label>
        </NativeTabs.Trigger>
      ))}
    </NativeTabs>
  );
}

function AndroidTabs() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: "#a855f7",
        tabBarInactiveTintColor: "#9ca3af",
        tabBarStyle: {
          backgroundColor: "#111827",
          borderTopColor: "#2f3347",
        },
      }}
    >
      {MAIN_TABS.map((tab) => (
        <Tabs.Screen
          key={tab.name}
          name={tab.name}
          options={{
            title: tab.title,
            tabBarIcon: ({ color, size }) => (
              <MaterialIcons
                name={tab.androidIcon as MaterialIconName}
                color={color}
                size={size}
              />
            ),
          }}
        />
      ))}
    </Tabs>
  );
}
