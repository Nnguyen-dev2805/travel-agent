from enum import Enum

class MemoryType(str, Enum):
    """Phân loại vùng nhớ."""
    SEMANTIC = "semantic"  # Dài hạn (Sở thích, thói quen, thông tin cá nhân)
    EPISODIC = "episodic"  # Sự kiện (Tóm tắt phiên chat)
    WORKING = "working"    # Ngắn hạn (Ngữ cảnh phiên chat hiện tại)

class FactType(str, Enum):
    """Phân loại Fact cho trí nhớ Semantic."""
    PREFERENCE = "preference"
    IDENTITY = "identity"
    VISITED_PLACE = "visited_place"
    BUDGET = "budget"
    TRAVEL_STYLE = "travel_style"
    DIETARY = "dietary"
    BEHAVIOR = "behavior"

class MemoryStatus(str, Enum):
    """Trạng thái vòng đời của Memory."""
    CANDIDATE = "candidate"     # Chờ đánh giá, chưa đưa vào RAG
    ACTIVE = "active"           # Đang sử dụng (mặc định cho RAG)
    REINFORCED = "reinforced"   # Quan trọng, được nhắc lại nhiều lần
    STALE = "stale"             # Đã lâu không truy cập
    ARCHIVED = "archived"       # Đóng băng, không RAG nhưng giữ lịch sử
    DEPRECATED = "deprecated"   # Bị thay thế bởi thông tin mới
    DELETED = "deleted"         # Đã xóa (Soft delete)

class ConflictAction(str, Enum):
    """Hành động khi phát hiện trùng lặp Fact."""
    SKIP = "skip"                           # Trùng lặp 100%, bỏ qua
    CREATE = "create"                       # Mới hoàn toàn
    UPDATE = "update"                       # Cập nhật thông tin cũ (VD: sửa budget)
    MERGE = "merge"                         # Ghép 2 thông tin lại với nhau
    DEPRECATE_AND_CREATE = "deprecate"      # Thông tin cũ sai/lỗi thời, tạo cái mới
    DELETE = "delete"                       # Đánh dấu xóa thông tin cũ
