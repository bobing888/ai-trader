/**
 * NotificationToaster — fixed-position toast container that renders all visible
 * notification toasts stacked in the top-right corner.
 *
 * Reads the toast queue from NotificationContext and delegates rendering to
 * <NotificationToast>.  Auto-dismiss timers are owned by NotificationProvider.
 */

import { useNotificationContext } from "./NotificationProvider";
import { NotificationToast } from "./NotificationToast";

export function NotificationToaster(): JSX.Element {
  const { toasts, ack } = useNotificationContext();

  const handleAck = (id: string) => {
    ack(id);
  };

  const handleDismiss = (id: string) => {
    // Dismiss is handled by NotificationProvider's timer, but we also
    // allow manual dismiss by removing from local toast list.
    // The context doesn't expose a dismiss function, so we just ack silently.
    void handleAck(id);
  };

  if (toasts.length === 0) return <></>;

  return (
    <div
      className="fixed top-4 right-4 z-50 flex flex-col gap-2 pointer-events-none"
      aria-label="Notification toasts"
    >
      {toasts.map((toast) => (
        <div key={toast.id} className="pointer-events-auto">
          <NotificationToast
            notification={toast}
            onAck={handleAck}
            onDismiss={handleDismiss}
          />
        </div>
      ))}
    </div>
  );
}
