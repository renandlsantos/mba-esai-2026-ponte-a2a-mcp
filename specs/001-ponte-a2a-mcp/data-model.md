# Modelo
Sala/Reserva mantêm formato original dos JSON. Reserva retornada acrescenta reservado/politica/motivo. Sobreposição: inicio<fimExistente e fim>inicioExistente, logo intervalos adjacentes não conflitam.

Estado MRTR interno: args originais, alternativas ordenadas, chave de pergunta. Selado por SDK com prazo600s e binding de request; nada guardado entre rodadas no servidor.

Task pública: id,contextId,status(state,message),history,artifacts. Privado: args,traceparent,requestState,questionKey,alternatives. Mapa por UUID e lock por Task. Transições submitted→working→completed|failed|input_required; input_required→working→completed|canceled|failed|input_required. Terminal não sai.
