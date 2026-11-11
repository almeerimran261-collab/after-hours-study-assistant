"""Local-only upload controls, kept separate from the public demo entrypoint."""
import streamlit as st

from src.local_workspace import LocalWorkspace, Upload, require_local


def _finish(workspace, message):
    st.session_state.upload_notice = message
    st.session_state.upload_picker_version = st.session_state.get("upload_picker_version", 0) + 1
    # These run before the collection selectbox is created in app.py.
    if workspace.collection is not None:
        st.session_state.collection_choice = workspace.collection.name
    else:
        st.session_state.pop("collection_choice", None)
    st.session_state.active_collection = None
    st.session_state.messages = []
    memory = st.session_state.get("question_memory")
    if memory is not None:
        memory.clear()
    st.rerun()


def render_local_uploads(load_model):
    require_local()
    if "upload_workspace" not in st.session_state:
        st.session_state.upload_workspace = LocalWorkspace()
    workspace = st.session_state.upload_workspace
    if "upload_notice" in st.session_state:
        st.session_state.local_upload_panel = True

    with st.sidebar.expander(
        "Upload documents", expanded=True, key="local_upload_panel", on_change="rerun",
    ):
        st.caption(
            "PDF/PPTX · up to 6 files · 20 MB each / 60 MB total · "
            "300 pages or slides."
        )
        st.caption(
            "Session only. A new batch replaces your uploads. "
            "Saved collections stay available."
        )
        with st.form("upload_form", border=False):
            uploads = st.file_uploader(
                "Choose study documents", type=["pdf", "pptx"],
                accept_multiple_files=True,
                max_upload_size=20,
                key=f"upload_picker_{st.session_state.get('upload_picker_version', 0)}",
            )
            # Form inputs arrive together on submit; keep this button enabled
            # even when the picker was empty on the preceding script run.
            index = st.form_submit_button(
                "Index selected files", use_container_width=True,
            )
        if index:
            try:
                # Validate file selection before loading a potentially uncached model.
                from src.local_workspace import validate_uploads
                files = validate_uploads(Upload(item.name, item.getvalue()) for item in uploads)
                with st.spinner("Loading the local embedding model…"):
                    model = load_model()
                bar = st.progress(0.0, text="Preparing documents…")
                workspace.replace(files, model, lambda value, text: bar.progress(value, text=text))
            except Exception as exc:
                st.error(f"Could not index this batch: {exc}")
                if workspace.collection is not None:
                    st.caption("Your previous uploaded batch is still available.")
            else:
                count = len(workspace.files)
                _finish(workspace, f"Ready: {count} document{'s' if count != 1 else ''} indexed.")

        if workspace.collection is not None:
            count = len(workspace.files)
            st.caption(f"Current upload batch · {count} document{'s' if count != 1 else ''}")
            with st.form("remove_uploads_form", border=False):
                st.caption("Select documents to remove:")
                remove = [
                    file.name for index, file in enumerate(workspace.files)
                    if st.checkbox(file.name, key=f"remove_upload_{workspace.collection.name}_{index}")
                ]
                remove_submitted = st.form_submit_button(
                    "Remove selected documents", use_container_width=True,
                )
            if remove_submitted:
                try:
                    if len(remove) == len(workspace.files):
                        workspace.clear()
                    else:
                        with st.spinner("Updating the uploaded documents…"):
                            model = load_model()
                            bar = st.progress(0.0, text="Rebuilding the remaining documents…")
                            workspace.remove(remove, model, lambda value, text: bar.progress(value, text=text))
                except Exception as exc:
                    st.error(f"Could not remove these documents: {exc}")
                else:
                    _finish(workspace, "Selected uploaded documents removed. Conversation cleared.")
            if st.button("Clear uploaded documents", use_container_width=True):
                try:
                    workspace.clear()
                except Exception as exc:
                    st.error(f"Could not clear uploaded documents: {exc}")
                else:
                    _finish(workspace, "Uploaded documents and conversation cleared.")
        notice = st.session_state.pop("upload_notice", None)
        if notice:
            st.success(notice)
        if workspace.warnings:
            st.warning("Some content could not be extracted. Check these notes before relying on answers.")
            for warning in workspace.warnings[:10]:
                st.caption(warning)
            if len(workspace.warnings) > 10:
                st.caption(f"{len(workspace.warnings) - 10} more extraction notices.")
    return workspace
