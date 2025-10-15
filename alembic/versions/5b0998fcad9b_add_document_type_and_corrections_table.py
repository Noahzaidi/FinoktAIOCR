"""add_document_type_and_corrections_table

Revision ID: 5b0998fcad9b
Revises: b06b4c7ae036
Create Date: 2025-10-14 21:27:58.931369

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON
import uuid


# revision identifiers, used by Alembic.
revision: str = '5b0998fcad9b'
down_revision: Union[str, Sequence[str], None] = 'b06b4c7ae036'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add document_type column to documents table
    op.add_column('documents', sa.Column('document_type', sa.String(), nullable=True, server_default='unknown'))
    
    # Create corrections table
    op.create_table(
        'corrections',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('document_id', sa.String(), nullable=False, index=True),
        sa.Column('page', sa.Integer()),
        sa.Column('word_id', sa.String()),
        sa.Column('original_text', sa.String(), nullable=False),
        sa.Column('corrected_text', sa.String(), nullable=False),
        sa.Column('corrected_bbox', JSON()),
        sa.Column('user_id', sa.String(), server_default='system'),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('correction_type', sa.String(), server_default='text_edit')
    )
    
    # Create index on document_id for faster queries
    op.create_index('ix_corrections_document_id', 'corrections', ['document_id'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop corrections table
    op.drop_index('ix_corrections_document_id', table_name='corrections')
    op.drop_table('corrections')
    
    # Remove document_type column from documents table
    op.drop_column('documents', 'document_type')
