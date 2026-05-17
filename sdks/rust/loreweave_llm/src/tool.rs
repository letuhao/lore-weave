//! Tool-call reassembly for streamed [`StreamEvent::ToolCall`] fragments.
//!
//! The canonical `tool_call` SSE event has **no per-index terminal marker**
//! (the gateway does not re-emit Anthropic's `content_block_stop`, and OpenAI
//! has no per-call terminator). The [`ToolCallAccumulator`] is therefore
//! index-keyed — a single turn may stream multiple tool calls with
//! interleaved / out-of-order `index` values — and is finalized only when the
//! caller knows the stream is over: the `Done` event, OR an error-terminated
//! stream. [`ToolCallAccumulator::finish`] salvages whatever arrived in
//! either case.

use std::collections::BTreeMap;

use crate::models::StreamEvent;

/// One tool call accumulated so far from `tool_call` fragments.
#[derive(Debug, Clone, Default)]
struct PartialToolCall {
    id: Option<String>,
    name: Option<String>,
    arguments: String,
}

/// A fully reassembled tool call drained from [`ToolCallAccumulator::finish`].
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CompletedToolCall {
    /// The provider's tool-call index within the turn.
    pub index: u32,
    /// Provider tool-call id (the first fragment for the index carries it).
    pub id: Option<String>,
    /// Tool/function name (the first fragment for the index carries it).
    pub name: Option<String>,
    /// The concatenated tool-call arguments JSON. MAY be empty if the
    /// provider never sent argument fragments — the caller surfaces that as a
    /// tool-use failure rather than treating it as an error here.
    pub arguments: String,
}

/// Reassembles streamed [`StreamEvent::ToolCall`] fragments into complete
/// tool calls. See the module docs for why finalization is caller-driven.
#[derive(Debug, Default)]
pub struct ToolCallAccumulator {
    /// Index-keyed — `BTreeMap` so `finish()` yields calls sorted by index
    /// regardless of the wire arrival order.
    calls: BTreeMap<u32, PartialToolCall>,
}

impl ToolCallAccumulator {
    /// A fresh, empty accumulator.
    pub fn new() -> Self {
        Self::default()
    }

    /// Feed one event. Non-`ToolCall` events are ignored, so a caller may
    /// pipe every [`StreamEvent`] through unconditionally.
    ///
    /// `id` / `name` are first-write-wins (later fragments for the same index
    /// usually omit them); `arguments_delta` is appended in arrival order.
    pub fn push(&mut self, event: &StreamEvent) {
        if let StreamEvent::ToolCall {
            index,
            id,
            name,
            arguments_delta,
        } = event
        {
            let entry = self.calls.entry(*index).or_default();
            if entry.id.is_none() {
                if let Some(id) = id {
                    entry.id = Some(id.clone());
                }
            }
            if entry.name.is_none() {
                if let Some(name) = name {
                    entry.name = Some(name.clone());
                }
            }
            entry.arguments.push_str(arguments_delta);
        }
    }

    /// True when no `tool_call` fragments have been accumulated.
    pub fn is_empty(&self) -> bool {
        self.calls.is_empty()
    }

    /// Number of distinct tool-call indices seen.
    pub fn len(&self) -> usize {
        self.calls.len()
    }

    /// Drain into completed tool calls, ascending by index. Safe after a
    /// `Done` event OR an error-terminated stream — salvages whatever
    /// fragments arrived.
    pub fn finish(self) -> Vec<CompletedToolCall> {
        self.calls
            .into_iter()
            .map(|(index, p)| CompletedToolCall {
                index,
                id: p.id,
                name: p.name,
                arguments: p.arguments,
            })
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn frag(index: u32, id: Option<&str>, name: Option<&str>, args: &str) -> StreamEvent {
        StreamEvent::ToolCall {
            index,
            id: id.map(String::from),
            name: name.map(String::from),
            arguments_delta: args.to_string(),
        }
    }

    #[test]
    fn reassembles_single_call_fragments() {
        let mut acc = ToolCallAccumulator::new();
        // First fragment carries id + name, empty arguments.
        acc.push(&frag(0, Some("call_a"), Some("submit"), ""));
        acc.push(&frag(0, None, None, r#"{"clas"#));
        acc.push(&frag(0, None, None, r#"sifications":[]}"#));
        let done = acc.finish();
        assert_eq!(done.len(), 1);
        assert_eq!(done[0].id.as_deref(), Some("call_a"));
        assert_eq!(done[0].name.as_deref(), Some("submit"));
        assert_eq!(done[0].arguments, r#"{"classifications":[]}"#);
    }

    #[test]
    fn handles_interleaved_out_of_order_indices() {
        // OpenAI may stream two calls with interleaved / non-monotonic index.
        let mut acc = ToolCallAccumulator::new();
        acc.push(&frag(1, Some("call_b"), Some("beta"), r#"{"b":"#));
        acc.push(&frag(0, Some("call_a"), Some("alpha"), r#"{"a":"#));
        acc.push(&frag(1, None, None, "2}"));
        acc.push(&frag(0, None, None, "1}"));
        let done = acc.finish();
        // finish() yields calls sorted ascending by index regardless of arrival.
        assert_eq!(done.len(), 2);
        assert_eq!(done[0].index, 0);
        assert_eq!(done[0].name.as_deref(), Some("alpha"));
        assert_eq!(done[0].arguments, r#"{"a":1}"#);
        assert_eq!(done[1].index, 1);
        assert_eq!(done[1].name.as_deref(), Some("beta"));
        assert_eq!(done[1].arguments, r#"{"b":2}"#);
    }

    #[test]
    fn id_name_first_write_wins() {
        let mut acc = ToolCallAccumulator::new();
        acc.push(&frag(0, Some("first"), Some("first_name"), ""));
        // A stray later id/name must not overwrite the first.
        acc.push(&frag(0, Some("second"), Some("second_name"), "x"));
        let done = acc.finish();
        assert_eq!(done[0].id.as_deref(), Some("first"));
        assert_eq!(done[0].name.as_deref(), Some("first_name"));
        assert_eq!(done[0].arguments, "x");
    }

    #[test]
    fn ignores_non_tool_call_events() {
        let mut acc = ToolCallAccumulator::new();
        acc.push(&StreamEvent::Token {
            delta: "hi".into(),
            index: None,
        });
        assert!(acc.is_empty());
        assert_eq!(acc.finish().len(), 0);
    }

    #[test]
    fn salvages_partial_call_with_empty_arguments() {
        // An error-terminated stream where only the first (id/name) fragment
        // arrived — finish() must still surface it, empty arguments and all.
        let mut acc = ToolCallAccumulator::new();
        acc.push(&frag(0, Some("call_a"), Some("submit"), ""));
        let done = acc.finish();
        assert_eq!(done.len(), 1);
        assert_eq!(done[0].arguments, "");
        assert_eq!(done[0].id.as_deref(), Some("call_a"));
    }
}
