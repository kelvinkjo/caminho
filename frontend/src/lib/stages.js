import { Sprout, Flame, Shield, Swords, Handshake, Crown } from "lucide-react";

export const STAGE_ICONS = {
  sprout: Sprout, flame: Flame, shield: Shield, swords: Swords, handshake: Handshake, crown: Crown,
};

export const DIMENSIONS = ["Oração", "Formação", "Comunidade", "Missão", "Vocação"];

export function statusMeta(status) {
  switch (status) {
    case "completed": return { label: "Concluída", cls: "text-orange-400" };
    case "current": return { label: "Etapa atual", cls: "text-orange-500" };
    case "awaiting_approval": return { label: "Aguardando avaliação", cls: "text-yellow-500" };
    default: return { label: "Bloqueada", cls: "text-stone-500" };
  }
}
