"""initial_schema_all_models

Revision ID: 5c6c874465c9
Revises:
Create Date: 2026-02-22 18:02:15.669653

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY, TEXT


# revision identifiers, used by Alembic.
revision: str = '5c6c874465c9'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Auth / Users ──
    op.create_table(
        'users',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('email', sa.String(255), unique=True, nullable=False),
        sa.Column('display_name', sa.String(255)),
        sa.Column('cluster', sa.String(50)),
        sa.Column('base_url', sa.String(255)),
        sa.Column('is_admin', sa.Boolean, default=False),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('last_login_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    op.create_table(
        'roles',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(100), unique=True, nullable=False),
        sa.Column('description', sa.String(500)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        'permissions',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('module', sa.String(100), nullable=False),
        sa.Column('operation', sa.String(100), nullable=False),
        sa.Column('description', sa.String(500)),
        sa.UniqueConstraint('module', 'operation', name='uq_permission_module_op'),
    )

    op.create_table(
        'user_roles',
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('role_id', sa.Integer, sa.ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('granted_by', sa.Integer, sa.ForeignKey('users.id')),
        sa.Column('granted_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        'user_permissions',
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('permission_id', sa.Integer, sa.ForeignKey('permissions.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('granted_by', sa.Integer, sa.ForeignKey('users.id')),
        sa.Column('granted_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        'role_permissions',
        sa.Column('role_id', sa.Integer, sa.ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('permission_id', sa.Integer, sa.ForeignKey('permissions.id', ondelete='CASCADE'), primary_key=True),
    )

    op.create_table(
        'user_orgs',
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('org_id', sa.Integer, primary_key=True),
        sa.Column('org_name', sa.String(255)),
    )

    # ── Extraction ──
    op.create_table(
        'extraction_runs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id')),
        sa.Column('org_id', sa.Integer),
        sa.Column('databricks_instance', sa.String(500)),
        sa.Column('root_path', sa.String(500)),
        sa.Column('modified_since', sa.DateTime),
        sa.Column('total_notebooks', sa.Integer, default=0),
        sa.Column('processed_notebooks', sa.Integer, default=0),
        sa.Column('skipped_notebooks', sa.Integer, default=0),
        sa.Column('total_sqls_extracted', sa.Integer, default=0),
        sa.Column('valid_sqls', sa.Integer, default=0),
        sa.Column('unique_hashes', sa.Integer, default=0),
        sa.Column('api_failures', sa.Integer, default=0),
        sa.Column('status', sa.String(50), default='running'),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
    )

    op.create_table(
        'extracted_sqls',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('run_id', UUID(as_uuid=True), sa.ForeignKey('extraction_runs.id', ondelete='CASCADE')),
        sa.Column('org_id', sa.String(50)),
        sa.Column('org_id_source', sa.String(100)),
        sa.Column('notebook_path', sa.Text, nullable=False),
        sa.Column('notebook_name', sa.String(500)),
        sa.Column('user_name', sa.String(255)),
        sa.Column('object_id', sa.String(100)),
        sa.Column('language', sa.String(50)),
        sa.Column('created_at', sa.DateTime(timezone=True)),
        sa.Column('modified_at', sa.DateTime(timezone=True)),
        sa.Column('cell_number', sa.Integer),
        sa.Column('file_type', sa.String(50)),
        sa.Column('cleaned_sql', sa.Text),
        sa.Column('sql_hash', sa.String(64)),
        sa.Column('is_valid', sa.Boolean, default=False),
        sa.Column('original_snippet', sa.Text),
        sa.Column('extracted_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_extracted_sqls_run_id', 'extracted_sqls', ['run_id'])
    op.create_index('ix_extracted_sqls_sql_hash', 'extracted_sqls', ['sql_hash'])

    op.create_table(
        'notebook_metadata',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('run_id', UUID(as_uuid=True), sa.ForeignKey('extraction_runs.id', ondelete='CASCADE')),
        sa.Column('notebook_path', sa.Text, nullable=False),
        sa.Column('notebook_name', sa.String(500)),
        sa.Column('user_name', sa.String(255)),
        sa.Column('object_id', sa.String(100)),
        sa.Column('language', sa.String(50)),
        sa.Column('created_at', sa.DateTime(timezone=True)),
        sa.Column('modified_at', sa.DateTime(timezone=True)),
        sa.Column('has_content', sa.Boolean, default=False),
        sa.Column('file_type', sa.String(50)),
        sa.Column('status', sa.String(50), default='Processed'),
        sa.Column('is_attached_to_jobs', sa.String(10), default='No'),
        sa.Column('job_id', sa.String(100)),
        sa.Column('job_name', sa.String(255)),
        sa.Column('cont_success_run_count', sa.Integer),
        sa.Column('earliest_run_date', sa.DateTime(timezone=True)),
        sa.Column('trigger_type', sa.String(50)),
        sa.Column('extracted_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_notebook_metadata_run_id', 'notebook_metadata', ['run_id'])

    # ── Analysis ──
    op.create_table(
        'analysis_runs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('run_id', UUID(as_uuid=True), sa.ForeignKey('extraction_runs.id')),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id')),
        sa.Column('org_id', sa.String(50)),
        sa.Column('counters', JSONB),
        sa.Column('clusters', JSONB),
        sa.Column('classified_filters', JSONB),
        sa.Column('fingerprints_summary', JSONB),
        sa.Column('literal_vals', JSONB),
        sa.Column('alias_conv', JSONB),
        sa.Column('total_weight', sa.Integer, default=0),
        sa.Column('version', sa.Integer, default=1),
        sa.Column('status', sa.String(50), default='running'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        'analysis_fingerprints',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('analysis_id', UUID(as_uuid=True), sa.ForeignKey('analysis_runs.id', ondelete='CASCADE')),
        sa.Column('qfp_id', sa.String(20), nullable=False),
        sa.Column('raw_sql', sa.Text),
        sa.Column('canonical_sql', sa.Text),
        sa.Column('nl_question', sa.Text),
        sa.Column('frequency', sa.Integer, default=1),
        sa.Column('tables_json', JSONB),
        sa.Column('columns_json', JSONB),
        sa.Column('functions_json', JSONB),
        sa.Column('join_graph_json', JSONB),
        sa.Column('where_json', JSONB),
        sa.Column('group_by_json', JSONB),
        sa.Column('having_json', JSONB),
        sa.Column('order_by_json', JSONB),
        sa.Column('literals_json', JSONB),
        sa.Column('case_when_json', JSONB),
        sa.Column('window_json', JSONB),
        sa.Column('structural_flags', JSONB),
        sa.Column('select_col_count', sa.Integer, default=0),
        sa.Column('alias_map_json', JSONB),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_analysis_fingerprints_analysis_id', 'analysis_fingerprints', ['analysis_id'])

    op.create_table(
        'analysis_notebooks',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('analysis_id', UUID(as_uuid=True), sa.ForeignKey('analysis_runs.id', ondelete='CASCADE')),
        sa.Column('notebook_id', sa.Integer, sa.ForeignKey('notebook_metadata.id', ondelete='CASCADE')),
        sa.Column('sql_count', sa.Integer, default=0),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_analysis_notebooks_analysis_id', 'analysis_notebooks', ['analysis_id'])
    op.create_index('ix_analysis_notebooks_notebook_id', 'analysis_notebooks', ['notebook_id'])

    # ── Context Documents ──
    op.create_table(
        'context_docs',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('source_type', sa.String(50), nullable=False),
        sa.Column('source_run_id', UUID(as_uuid=True)),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id')),
        sa.Column('org_id', sa.String(50)),
        sa.Column('doc_key', sa.String(100), nullable=False),
        sa.Column('doc_name', sa.String(255)),
        sa.Column('doc_content', sa.Text),
        sa.Column('model_used', sa.String(100)),
        sa.Column('provider_used', sa.String(50)),
        sa.Column('system_prompt_used', sa.Text),
        sa.Column('payload_sent', JSONB),
        sa.Column('inclusions_used', JSONB),
        sa.Column('token_count', sa.Integer),
        sa.Column('status', sa.String(50), default='active'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        'managed_contexts',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('org_id', sa.Integer, nullable=False),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id')),
        sa.Column('capillary_context_id', sa.String(100)),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('content', sa.Text),
        sa.Column('scope', sa.String(20), default='org'),
        sa.Column('source', sa.String(50)),
        sa.Column('source_doc_id', sa.Integer, sa.ForeignKey('context_docs.id')),
        sa.Column('is_uploaded', sa.Boolean, default=False),
        sa.Column('uploaded_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_managed_contexts_org_id', 'managed_contexts', ['org_id'])

    op.create_table(
        'refactoring_runs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id')),
        sa.Column('org_id', sa.Integer, nullable=False),
        sa.Column('input_context_ids', ARRAY(sa.Integer)),
        sa.Column('blueprint_text', sa.Text),
        sa.Column('model_used', sa.String(100)),
        sa.Column('provider_used', sa.String(50)),
        sa.Column('output_raw', sa.Text),
        sa.Column('output_parsed', JSONB),
        sa.Column('token_usage', JSONB),
        sa.Column('status', sa.String(50), default='running'),
        sa.Column('error_message', sa.Text),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
    )

    # ── Source Extractions (Confluence, Config APIs) ──
    op.create_table(
        'confluence_extractions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id')),
        sa.Column('org_id', sa.Integer),
        sa.Column('space_key', sa.String(50)),
        sa.Column('space_name', sa.String(255)),
        sa.Column('page_ids', ARRAY(TEXT)),
        sa.Column('extracted_content', JSONB),
        sa.Column('status', sa.String(50), default='running'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
    )

    op.create_table(
        'config_api_extractions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id')),
        sa.Column('org_id', sa.Integer, nullable=False),
        sa.Column('api_type', sa.String(100), nullable=False),
        sa.Column('extracted_data', JSONB),
        sa.Column('processed_summary', sa.String),
        sa.Column('status', sa.String(50), default='running'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
    )

    # ── Audit Log ──
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id')),
        sa.Column('user_email', sa.String(255)),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('module', sa.String(100)),
        sa.Column('resource_type', sa.String(100)),
        sa.Column('resource_id', sa.String(100)),
        sa.Column('details', JSONB),
        sa.Column('ip_address', sa.String(45)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'])
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'])

    # ── Chat ──
    op.create_table(
        'chat_conversations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('org_id', sa.Integer, nullable=False),
        sa.Column('title', sa.String(255), default='New Chat'),
        sa.Column('provider', sa.String(50), default='anthropic'),
        sa.Column('model', sa.String(100), default='claude-sonnet-4-20250514'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_chat_conversations_user_id', 'chat_conversations', ['user_id'])
    op.create_index('ix_chat_conversations_org_id', 'chat_conversations', ['org_id'])

    op.create_table(
        'chat_messages',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('conversation_id', UUID(as_uuid=True), sa.ForeignKey('chat_conversations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content', sa.Text),
        sa.Column('tool_calls', JSONB),
        sa.Column('tool_results', JSONB),
        sa.Column('token_usage', JSONB),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_chat_messages_conversation_id', 'chat_messages', ['conversation_id'])


def downgrade() -> None:
    op.drop_table('chat_messages')
    op.drop_table('chat_conversations')
    op.drop_table('audit_logs')
    op.drop_table('config_api_extractions')
    op.drop_table('confluence_extractions')
    op.drop_table('refactoring_runs')
    op.drop_table('managed_contexts')
    op.drop_table('context_docs')
    op.drop_table('analysis_notebooks')
    op.drop_table('analysis_fingerprints')
    op.drop_table('analysis_runs')
    op.drop_table('notebook_metadata')
    op.drop_table('extracted_sqls')
    op.drop_table('extraction_runs')
    op.drop_table('user_orgs')
    op.drop_table('role_permissions')
    op.drop_table('user_permissions')
    op.drop_table('user_roles')
    op.drop_table('permissions')
    op.drop_table('roles')
    op.drop_table('users')
