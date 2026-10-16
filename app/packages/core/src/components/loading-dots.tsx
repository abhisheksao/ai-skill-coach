import { useEffect, useState } from 'react';
import { Animated, StyleSheet, View } from 'react-native';

import { spacing, useTheme } from '../theme/tokens';

/** Pending-reply indicator shown while the coach is thinking. */
export function LoadingDots() {
  const { colors } = useTheme();
  const [pulse] = useState(() => new Animated.Value(0.3));

  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1, duration: 500, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 0.3, duration: 500, useNativeDriver: true }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [pulse]);

  return (
    <View style={styles.row} accessibilityLabel="loading">
      {[0, 1, 2].map((i) => (
        <Animated.View
          key={i}
          style={[styles.dot, { backgroundColor: colors.textMuted, opacity: pulse }]}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  dot: { borderRadius: 4, height: 8, marginRight: spacing.xs, width: 8 },
  row: { flexDirection: 'row', padding: spacing.sm },
});
