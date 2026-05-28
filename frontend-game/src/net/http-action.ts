// One-shot HTTP action stub for non-streaming commands (e.g. login,
// match-request). Session E+ wires concrete fetch through api-gateway-bff.

export async function postAction<TReq, TRes>(_path: string, _body: TReq): Promise<TRes> {
  throw new Error('http-action not yet implemented — Session E');
}
