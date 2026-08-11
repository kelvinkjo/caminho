import { Room, RoomEvent, Track, createLocalTracks } from "livekit-client";

// Conecta como espectador (subscribe-only) e anexa vídeo/áudio remotos ao container.
export async function connectViewer({ serverUrl, token, onVideo, onStatus }) {
  const room = new Room({ adaptiveStream: true, dynacast: true });
  room.on(RoomEvent.TrackSubscribed, (track) => {
    if (track.kind === Track.Kind.Video || track.kind === Track.Kind.Audio) {
      onVideo?.(track);
    }
  });
  room.on(RoomEvent.Disconnected, () => onStatus?.("disconnected"));
  room.on(RoomEvent.Reconnecting, () => onStatus?.("reconnecting"));
  room.on(RoomEvent.Reconnected, () => onStatus?.("connected"));
  await room.connect(serverUrl, token);
  onStatus?.("connected");
  return room;
}

// Conecta como transmissor e publica câmera/microfone com os dispositivos escolhidos.
export async function connectBroadcaster({ serverUrl, token, videoDeviceId, audioDeviceId, onStatus }) {
  const room = new Room({ adaptiveStream: true, dynacast: true });
  room.on(RoomEvent.Disconnected, () => onStatus?.("disconnected"));
  room.on(RoomEvent.Reconnecting, () => onStatus?.("reconnecting"));
  room.on(RoomEvent.Reconnected, () => onStatus?.("connected"));
  await room.connect(serverUrl, token);
  const tracks = await createLocalTracks({
    audio: audioDeviceId ? { deviceId: audioDeviceId } : true,
    video: videoDeviceId ? { deviceId: videoDeviceId } : true,
  });
  for (const t of tracks) await room.localParticipant.publishTrack(t);
  onStatus?.("connected");
  return { room, tracks };
}

export async function listDevices() {
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    return {
      cameras: devices.filter((d) => d.kind === "videoinput"),
      microphones: devices.filter((d) => d.kind === "audioinput"),
    };
  } catch {
    return { cameras: [], microphones: [] };
  }
}
