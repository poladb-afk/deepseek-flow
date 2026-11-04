// exp/109: techo de turnos para el brazo pi.
//
// pi NO trae un límite de turnos integrado (el corte se hace desde el propio
// agente con finishTurn); el pre-registro (banco/specs/exp109_benchmark_externo.md,
// X145) fija el mismo techo de 16 que flow (MAX_TOOL_ROUNDS, S6) y mini
// (agent.step_limit=16). Esta extensión lo implementa con los eventos públicos:
// cuenta los turnos y, al llegar a 16, bloquea las tool calls con un motivo
// visible para que el modelo cierre con lo que tenga. Las vueltas de cierre
// quedan en el stdout y se reportan.
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

const TECHO = 16;

export default function (pi: ExtensionAPI) {
  let turnos = 0;
  let cortado = false;
  pi.on("turn_end", async () => {
    turnos += 1;
    if (turnos >= TECHO) cortado = true;
  });
  pi.on("tool_call", async () => {
    if (!cortado) return undefined;
    return {
      block: true,
      reason: `tope de ${TECHO} turnos (exp/109): no hay más tools; respondé con lo que tengas`,
    };
  });
}
