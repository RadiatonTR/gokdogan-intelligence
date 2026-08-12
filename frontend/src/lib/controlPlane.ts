import { primeAdminSession } from '@/lib/adminSession';
import type {
  DesktopControlCapability,
  DesktopControlSessionProfile,
} from '@/lib/desktopControlContract';
import {
  canInvokeLocalControl,
  hasLocalControlBridge,
  localControlFetch,
} from '@/lib/localControlTransport';

type ControlPlaneOptions = RequestInit & {
  requireAdminSession?: boolean;
  capabilityIntent?: DesktopControlCapability;
  sessionProfileHint?: DesktopControlSessionProfile;
  enforceProfileHint?: boolean;
};

export async function controlPlaneFetch(
  path: string,
  options: ControlPlaneOptions = {},
): Promise<Response> {
  const {
    requireAdminSession = true,
    capabilityIntent,
    sessionProfileHint,
    enforceProfileHint,
    ...init
  } = options;
  const nativePrivilegedPath = hasLocalControlBridge() && canInvokeLocalControl(path, init);
  if (requireAdminSession && !nativePrivilegedPath) {
    await primeAdminSession();
  }
  return localControlFetch(path, {
    ...init,
    capabilityIntent,
    sessionProfileHint,
    enforceProfileHint,
  });
}

export async function controlPlaneJson<T>(
  path: string,
  options: ControlPlaneOptions = {},
): Promise<T> {
  const res = await controlPlaneFetch(path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data?.ok === false) {
    const fallback =
      res.status === 429
        ? 'control_plane_rate_limited'
        : res.status === 530
          ? 'local_control_plane_unavailable'
          : res.status === 502
            ? 'backend_unavailable'
        : `control_plane_request_failed:${res.status || 'unknown'}`;
    throw new Error(data?.detail || data?.message || data?.error || fallback);
  }
  return data as T;
}
