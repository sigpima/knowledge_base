# main_mcp.py
from decimal import Decimal
from typing import Any, Dict, Optional

from mcp.server.mcpserver import MCPServer
from sqlalchemy import text as sql_text

from app.core.services.knowledge_service import KnowledgeService
from app.domains.quotation.application.dto import EstimationData, EstimationWorkItemData
from app.infrastructure.config.config import settings
from app.infrastructure.database.postgres.readonly_session import ReadonlySessionLocal
from app.mcp.sql_guard import ensure_limit, validate_select_only

mcp = MCPServer("knowledge-base")
# Chỉ kết nối bằng role Postgres chỉ đọc: server MCP không bao giờ ghi DB.
knowledge_service = KnowledgeService(session_factory=ReadonlySessionLocal)
RUN_SQL_MAX_ROWS = 200


def _decimal_to_str(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None

def _jsonify(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _jsonify(v) for key, v in value.items()}
    if isinstance(value, list):
        return [_jsonify(v) for v in value]
    return value

def _format_estimation_work_item(detail: "EstimationWorkItemData") -> Dict[str, Any]:
    labor_info = None
    if detail.labor_info is not None:
        labor_info = {
            "area": _decimal_to_str(detail.labor_info.area),
            "final_unit_price_type": detail.labor_info.final_unit_price_type,
            "labor_coeff": _decimal_to_str(detail.labor_info.labor_coeff),
            "labor_unit_price": _decimal_to_str(detail.labor_info.labor_unit_price),
            "main_out_unit_price": _decimal_to_str(detail.labor_info.main_out_unit_price),
            "sub_out_unit_price": _decimal_to_str(detail.labor_info.sub_out_unit_price),
            "processes": [
                {
                    "name": p.name,
                    "days": _decimal_to_str(p.days),
                    "kn_manday": _decimal_to_str(p.kn_manday),
                    "main_out_manday": _decimal_to_str(p.main_out_manday),
                    "sub_out_manday": _decimal_to_str(p.sub_out_manday),
                }
                for p in detail.labor_info.processes
            ],
        }

    return {
        "cost_item_id": detail.cost_item_id,
        "item_id": detail.item_id,
        "name": detail.name,
        "material_unit_price": _decimal_to_str(detail.material_unit_price),
        "labor_unit_price": _decimal_to_str(detail.labor_unit_price),
        "profit_margin": _decimal_to_str(detail.profit_margin),
        "labor_info": labor_info,
        "main_materials": [
            {
                "product_name": m.product_name,
                "product_line": m.product_line,
                "unit_price_per_m2": _decimal_to_str(m.unit_price_per_m2),
                "percent_usage": _decimal_to_str(m.percent_usage),
            }
            for m in detail.main_materials
        ],
    }

def _format_estimation(estimation: "EstimationData") -> Dict[str, Any]:
    return {
        "estimation_id": estimation.estimation_id,
        "project_id": estimation.project_id,
        "total_price": _decimal_to_str(estimation.total_price),
        "total_details": [
            {
                "type": d.type,
                "name": d.name,
                "price": _decimal_to_str(d.price),
            }
            for d in estimation.total_details
        ],
        "labor_summary": {
            "total_kn_manday": _decimal_to_str(estimation.labor_summary.total_kn_manday),
            "total_main_out_manday": _decimal_to_str(estimation.labor_summary.total_main_out_manday),
            "total_sub_out_manday": _decimal_to_str(estimation.labor_summary.total_sub_out_manday),
            "total_out_manday": _decimal_to_str(estimation.labor_summary.total_out_manday),
            "total_manday": _decimal_to_str(estimation.labor_summary.total_manday),
        },
        "cost_breakdown": {
            "quotation_total_amount": _decimal_to_str(estimation.cost_breakdown.quotation_total_amount),
            "material_total": _decimal_to_str(estimation.cost_breakdown.material_total),
            "material_pct": _decimal_to_str(estimation.cost_breakdown.material_pct),
            "labor_total": _decimal_to_str(estimation.cost_breakdown.labor_total),
            "labor_pct": _decimal_to_str(estimation.cost_breakdown.labor_pct),
            "by_type": [
                {
                    "type": item.type,
                    "price": _decimal_to_str(item.price),
                    "pct_of_quotation_total": _decimal_to_str(item.pct_of_quotation_total),
                }
                for item in estimation.cost_breakdown.by_type
            ],
        },
    }

def _format_quotation_detail(quotation: Dict[str, Any]) -> Dict[str, Any]:
    quotation["total_amount"] = _decimal_to_str(quotation["total_amount"])
    quotation["issue_date"] = quotation["issue_date"].isoformat() if quotation["issue_date"] else None
    for package in quotation["packages"]:
        package["total_amount"] = _decimal_to_str(package["total_amount"])
        for work_item in package["work_items"]:
            work_item["quantity"] = _decimal_to_str(work_item["quantity"])
            work_item["unit_price"] = _decimal_to_str(work_item["unit_price"])
            work_item["total_price"] = _decimal_to_str(work_item["total_price"])
            # Same embed as get_work_item's "estimation" field -- the price
            # itself lives on the báo giá side above, but what it's made of
            # (vật tư/nhân công/lợi nhuận) only lives in dự toán, so a
            # quotation's work items aren't fully explained without it.
            estimation_detail = knowledge_service.get_estimation_work_item(work_item["item_id"])
            work_item["estimation"] = (
                None if estimation_detail is None else _format_estimation_work_item(estimation_detail)
            )
    return quotation


### PROJECT TOOL ###


@mcp.tool()
def get_project_overview(project_id: int) -> Dict[str, Any] | None:
    """Lấy tóm tắt đầy đủ 1 dự án (công trình) theo project_id, gộp cả
    phía báo giá lẫn dự toán trong 1 lần gọi -- dùng cho câu hỏi kiểu
    "cho tôi biết về công trình X". Trả về None nếu project_id không tồn
    tại. quotation_summary là số báo giá, số package, số hạng mục, tổng
    tiền báo giá trên toàn bộ báo giá thuộc công trình này. estimation là
    tổng hợp dự toán (total_price, total_details -- breakdown chi
    phí/lợi nhuận theo loại, labor_summary -- tổng manday, cost_breakdown
    -- % mỗi loại chi phí trên tổng báo giá) khi công trình có dữ liệu dự
    toán, hoặc None nếu công trình này chưa có dự toán -- báo giá và dự
    toán là hai tập dữ liệu độc lập, thiếu dự toán không phải là lỗi."""
    quotation_summary = knowledge_service.summarize_project(project_id)
    if quotation_summary is None:
        return None
    quotation_summary["total_amount"] = _decimal_to_str(quotation_summary["total_amount"])
    estimation = knowledge_service.get_estimation(project_id)
    return {
        "project_id": quotation_summary["project_id"],
        "project_name": quotation_summary["project_name"],
        "quotation_summary": quotation_summary,
        "estimation": None if estimation is None else _format_estimation(estimation),
    }


@mcp.tool()
def compare_project_cost_breakdown(project_id: int, cost_type: str) -> Dict[str, Any] | None:
    """So sánh % của 1 loại chi phí trên tổng báo giá (quotation_total_amount
    = SUM total_amount của mọi báo giá thuộc dự án) của 1 công trình với
    mọi công trình khác cũng có dự toán. cost_type nhận 2 dạng viết tắt --
    "material" (vật tư chính + vật tư phụ) và "labor" (nhân công), khớp
    đúng với 2 rollup cost_breakdown trong get_project_overview's estimation
    field -- hoặc bất kỳ
    chuỗi nào khác, khớp không phân biệt hoa/thường và khoảng trắng với
    giá trị TotalDetail.type thực tế (vd "chi phí khác", "chi phí bảo
    hành", "lợi nhuận thuần"); TotalDetail.type
    là text tự do, không phải enum ràng buộc trong DB, nên cost_type
    không khớp với gì trong dữ liệu sẽ trả về price=0/pct_of_total=0.00
    cho mọi công trình thay vì báo lỗi -- bản thân điều đó cũng là thông
    tin hữu ích (không có gì khớp với chuỗi đó). Trả về None nếu
    project_id không tồn tại hoặc không có dòng dự toán. Trả về
    price/pct_of_total của chính công trình mục tiêu, cộng thêm
    avg_pct_of_total/min_pct_of_total/max_pct_of_total trên mọi công
    trình có thể so sánh (có Estimation và quotation_total_amount khác
    0) và pct_point_diff_from_avg (target_pct - avg_pct, là chênh lệch
    ĐIỂM PHẦN TRĂM, không phải tỉ lệ -- vd 35% so với trung bình 30% là
    chênh lệch 5.00, không phải 16.67). matched_projects liệt kê tối đa
    10 công trình có pct_of_total cao nhất (tổng số thực sự nằm ở
    matched_count) -- công trình thiếu hẳn cost_type được yêu cầu vẫn
    đóng góp price=0 thay vì bị loại ra, theo đúng quy ước đã ghi của
    TotalDetail là 1 công trình có thể thiếu vài loại."""
    result = knowledge_service.compare_project_cost_breakdown(project_id, cost_type)
    if result is None:
        return None
    for key in ("price", "quotation_total_amount", "pct_of_total", "avg_pct_of_total",
                "min_pct_of_total", "max_pct_of_total", "pct_point_diff_from_avg"):
        result[key] = _decimal_to_str(result[key])
    for matched in result["matched_projects"]:
        matched["price"] = _decimal_to_str(matched["price"])
        matched["pct_of_total"] = _decimal_to_str(matched["pct_of_total"])
    return result


### QUOTATION TOOL ###


@mcp.tool()
def get_quotation(quotation_id: int) -> Dict[str, Any] | None:
    """Lấy chi tiết đầy đủ của 1 báo giá theo quotation_id: mã báo giá, dự
    án, ngày phát hành, tổng tiền, và toàn bộ packages -- mỗi package kèm
    danh sách work_item (item_id, tên, đơn vị, số lượng, đơn giá, thành
    tiền). Mỗi work_item còn có field estimation chứa chi tiết dự toán của
    cùng hạng mục đó (giống hệt get_work_item's estimation field: vật tư
    chính, nhân công theo quy trình, lợi nhuận -- các thành phần cấu
    thành nên unit_price phía trên), None khi hạng mục chưa có dữ liệu dự
    toán tương ứng. Trả về None nếu quotation_id không tồn tại."""
    quotation = knowledge_service.get_quotation(quotation_id)
    if quotation is None:
        return None
    return _format_quotation_detail(quotation)


@mcp.tool()
def find_quotations(
    project_id: Optional[int] = None,
    order_by: str = "issue_date_desc",
    limit: int = 1,
) -> Dict[str, Any]:
    """Lọc/sắp xếp báo giá và trả về CHI TIẾT ĐẦY ĐỦ (giống hệt get_quotation,
    gồm cả packages/work_items và field estimation dự toán trên mỗi
    work_item) cho các báo giá khớp nhất -- dùng cho câu
    hỏi kiểu "báo giá mới nhất tổng bao nhiêu", "báo giá cao nhất của
    công trình X là báo giá nào" mà không cần biết trước quotation_id, và
    để có sẵn chi tiết trong context nhằm trả lời nhanh các câu hỏi
    follow-up (vd "hạng mục nào đắt nhất trong đó") mà không cần gọi thêm
    tool. project_id lọc theo 1 công trình cụ thể, bỏ trống để tìm trên
    toàn bộ dữ liệu. order_by nhận 1 trong 4 giá trị: "issue_date_desc"
    (mặc định, mới nhất trước), "issue_date_asc" (cũ nhất trước),
    "total_amount_desc" (tổng tiền cao nhất trước), "total_amount_asc"
    (thấp nhất trước) -- giá trị khác sẽ trả về lỗi trong "error", không
    âm thầm dùng mặc định. limit tối đa 3 (giá trị lớn hơn tự bị hạ
    xuống 3) vì mỗi báo giá trả về nguyên chi tiết package/work_item, có
    thể khá nặng nếu lấy nhiều. Trả về quotations (danh sách, có thể
    rỗng) và matched_count -- tổng số báo giá khớp filter (project_id,
    không tính limit), để biết danh sách có bị cắt bớt hay không."""
    capped_limit = min(limit, 3)
    result = knowledge_service.find_quotations(project_id, order_by, capped_limit)
    if result is None:
        return {
            "error": (
                f"order_by không hợp lệ: {order_by!r}. Chỉ chấp nhận "
                "'issue_date_desc', 'issue_date_asc', 'total_amount_desc', 'total_amount_asc'."
            )
        }

    quotations, matched_count = result
    return {
        "quotations": [_format_quotation_detail(q) for q in quotations],
        "matched_count": matched_count,
    }


### WORK ITEM TOOL ###


@mcp.tool()
def get_work_item(item_id: int) -> Dict[str, Any] | None:
    """Tra cứu 1 hạng mục (work item) theo item_id: tên, mô tả, số lượng,
    đơn vị, đơn giá, thành tiền (phía báo giá). Trường estimation chứa
    chi tiết dự toán của cùng hạng mục này (vật tư chính, nhân công theo
    quy trình, lợi nhuận -- các thành phần cấu thành nên unit_price phía
    trên) khi có, hoặc None nếu hạng mục này chưa có dữ liệu dự toán
    tương ứng -- báo giá và dự toán liên kết lỏng theo thiết kế, thiếu
    không phải là lỗi."""
    work_item = knowledge_service.get_work_item(item_id)
    if work_item is None:
        return None
    estimation_detail = knowledge_service.get_estimation_work_item(item_id)
    return {
        "item_id": work_item.item_id,
        "name": work_item.name,
        "description": work_item.description,
        "quantity": _decimal_to_str(work_item.quantity),
        "unit": work_item.unit,
        "unit_price": _decimal_to_str(work_item.unit_price),
        "currency": work_item.currency,
        "total_price": _decimal_to_str(work_item.total_price),
        "estimation": None if estimation_detail is None else _format_estimation_work_item(estimation_detail),
    }


@mcp.tool()
def search_work_items(
    text: Optional[str] = None,
    concept_filters: Optional[Dict[str, str]] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """Tìm kiếm tự do theo tên/mô tả hạng mục, có thể lọc thêm theo cặp
    concept type->name (vd {"category": "Ngoại thất"}). Trả về items
    (tối đa `limit` dòng) và matched_count -- tổng số kết quả thực sự
    khớp; items chỉ bị cắt bớt khi matched_count > len(items), mỗi dòng
    trả về đều là kết quả khớp thật, đầy đủ, không cần xác minh lại bằng
    run_readonly_sql."""
    result = knowledge_service.search_work_items(text=text, concept_filters=concept_filters, limit=limit)
    for item in result["items"]:
        item["unit_price"] = _decimal_to_str(item["unit_price"])
    return result


@mcp.tool()
def compare_work_item_price(item_id: int) -> Dict[str, Any] | None:
    """So sánh đơn giá của 1 hạng mục đã ingest với các hạng mục lịch sử
    tương tự (khớp theo concept category/application/object và độ tương
    đồng tên). matched_items liệt kê tối đa 10 hạng mục lịch sử khớp gần
    nhất theo độ tương đồng tên (item_id, name, project_name, unit_price);
    matched_count là tổng số khớp thực sự, có thể lớn hơn len(matched_items).
    Mỗi phần tử matched_items còn có name_similarity_score (0-1, từ so
    sánh tên) -- điểm thấp báo hiệu đã dùng fallback lọc theo concept vì
    không có ứng viên nào vượt ngưỡng tương đồng tên; coi những kết quả
    này là khớp với độ tin cậy thấp hơn."""
    result = knowledge_service.compare_work_item_price(item_id)
    if result is None:
        return None
    for key in ("historical_min", "historical_max", "historical_avg"):
        result[key] = _decimal_to_str(result[key])
    for matched_item in result["matched_items"]:
        matched_item["unit_price"] = _decimal_to_str(matched_item["unit_price"])
    return result


@mcp.tool()
def compare_work_item_detail(item_id_a: int, item_id_b: int) -> Dict[str, Any] | None:
    """So sánh chi tiết dự toán của 2 hạng mục để giải thích TẠI SAO đơn
    giá báo giá (unit_price) của chúng khác nhau (vật liệu, quy
    trình, nhân công). Trả về None nếu 1 trong 2 item_id không tồn tại,
    hoặc bên nào đó không có dòng dự toán (không có gì để so sánh). Cấp
    cao nhất: unit_price_a/b (đơn giá báo giá quan sát được) và
    price_diff/price_diff_pct, sau đó material_unit_price/labor_unit_price/
    profit_margin mỗi cái đều có _a/_b/_diff riêng. Quan hệ giữa các
    thành phần là NHÂN, không phải CỘNG: (material_unit_price +
    labor_unit_price) * (1 + profit_margin) ≈ unit_price (xấp xỉ, có sai
    số làm tròn) -- nên material_unit_price_diff và labor_unit_price_diff
    KHÔNG cộng lại bằng price_diff, vì cả hai đều bị nhân thêm
    profit_margin trước khi ra giá cuối. profit_margin là tỉ lệ/phân số
    (vd 0.2 nghĩa là 20%), không phải số tiền VND, nên profit_margin_diff
    là chênh lệch điểm-tỉ-lệ và không so sánh trực tiếp về độ lớn với
    material_unit_price_diff/labor_unit_price_diff (là VND) được.
    labor_unit_price đã bao gồm sẵn tác động của labor_coeff -- khi giải
    thích chênh lệch giá, đừng cộng thêm labor_info_diff.labor_coeff_diff
    vào labor_unit_price_diff nữa, sẽ bị tính trùng. So sánh 3 khoản diff
    vẫn cho biết thành phần nào thay đổi và theo chiều nào, chỉ là tổng
    của chúng không khớp chính xác bằng price_diff. labor_info_diff là
    None trừ khi CẢ HAI bên đều có dòng labor_info (final_unit_price_type,
    labor_coeff, và từng chỉ số manday, mỗi cái đều có _a/_b/_diff).
    materials/processes là danh sách {match_type: "matched"|"only_a"|"only_b",
    name_similarity_score, a, b} -- các dòng ở 2 bên được ghép cặp theo
    độ tương đồng tên sản phẩm/quy trình (ngưỡng >= 0.5, chặt hơn ngưỡng
    0.4 của compare_work_item_price, vì ghép sai ở đây sẽ báo nhầm 2 vật
    liệu khác nhau thành 1 vật liệu bị thay đổi) bằng thuật toán ghép
    greedy một-một; các dòng không ghép được sẽ xuất hiện dưới dạng
    only_a/only_b thay vì bị ép ghép cặp với độ tin cậy thấp. Mỗi cặp đã
    ghép có snapshot a/b gồm product_name/layers/construction_loss/
    theoretical_rate/unit_price_per_m2/total_price_area_based (vật liệu)
    hoặc name/main_labors_kn/main_labors_out/sub_labors_out/days/
    kn_manday/main_out_manday/sub_out_manday (quy trình) -- đọc song song
    2 bên thay vì đã trừ sẵn, vì một số trường (product_name, layers)
    không phải số. Lưu ý: "hiện trạng" (site condition) không được biểu
    diễn trong schema này -- nếu breakdown vật liệu/nhân công/lợi nhuận
    không giải thích hết được price_diff quan sát được, hãy nói rõ điều
    đó thay vì đoán nguyên nhân không có dữ liệu hỗ trợ."""
    result = knowledge_service.compare_work_item_detail(item_id_a, item_id_b)
    if result is None:
        return None

    for key in ("unit_price_a", "unit_price_b", "price_diff", "price_diff_pct",
                "material_unit_price_a", "material_unit_price_b", "material_unit_price_diff",
                "labor_unit_price_a", "labor_unit_price_b", "labor_unit_price_diff",
                "profit_margin_a", "profit_margin_b", "profit_margin_diff"):
        result[key] = _decimal_to_str(result[key])

    if result["labor_info_diff"] is not None:
        for key in ("labor_coeff_a", "labor_coeff_b", "labor_coeff_diff",
                    "kn_manday_a", "kn_manday_b", "kn_manday_diff",
                    "main_out_manday_a", "main_out_manday_b", "main_out_manday_diff",
                    "sub_out_manday_a", "sub_out_manday_b", "sub_out_manday_diff",
                    "area_a", "area_b", "area_diff"):
            result["labor_info_diff"][key] = _decimal_to_str(result["labor_info_diff"][key])

    for material in result["materials"]:
        for side in ("a", "b"):
            if material[side] is not None:
                for key in ("construction_loss", "theoretical_rate", "unit_price_per_m2", "total_price_area_based"):
                    material[side][key] = _decimal_to_str(material[side][key])

    for process in result["processes"]:
        for side in ("a", "b"):
            if process[side] is not None:
                for key in ("days", "kn_manday", "main_out_manday", "sub_out_manday"):
                    process[side][key] = _decimal_to_str(process[side][key])

    return result


### ESTIMATION TOOL ###


@mcp.tool()
def compare_labor_cost(project_id: int) -> Dict[str, Any] | None:
    """So sánh tổng chi phí thuê thợ ngoài (main_out_total_price +
    sub_out_total_price cộng dồn trên toàn bộ dự toán) của 1 công trình
    với các công trình khác cũng có dự toán. Các ứng viên được xếp hạng
    theo điểm tương đồng: 50% mức gần nhau về diện tích (tổng
    LaborInfo.area) và 50% mức trùng lặp hạng mục/concept-tag (Jaccard
    trên concept của các work-item mỗi dự án) -- không có ngưỡng tương
    đồng tối thiểu, mọi công trình có thể so sánh đều được chấm điểm, nên
    matched_projects luôn hiện ra công trình gần nhất hiện có kể cả khi
    độ tương đồng thấp. Trả về None nếu project_id không tồn tại hoặc
    không có dòng dự toán nào. matched_projects liệt kê tối đa 10 kết quả
    gần nhất (project_id, name, total_out_cost, total_area, cost_diff =
    chi phí của họ trừ đi chi phí của công trình này, cost_diff_pct,
    similarity_score); matched_count là tổng số công trình có thể so
    sánh thực sự, có thể lớn hơn len(matched_projects)."""
    result = knowledge_service.compare_project_labor_cost(project_id)
    if result is None:
        return None
    result["total_out_cost"] = _decimal_to_str(result["total_out_cost"])
    result["total_area"] = _decimal_to_str(result["total_area"])
    for matched in result["matched_projects"]:
        matched["total_out_cost"] = _decimal_to_str(matched["total_out_cost"])
        matched["total_area"] = _decimal_to_str(matched["total_area"])
        matched["cost_diff"] = _decimal_to_str(matched["cost_diff"])
        matched["cost_diff_pct"] = _decimal_to_str(matched["cost_diff_pct"])
    return result


### BACKUP TOOL ###


@mcp.tool()
def run_readonly_sql(query: str) -> Dict[str, Any]:
    """Chạy 1 câu SQL SELECT tuỳ ý (chỉ đọc) trên schema quotation, dùng
    cho các câu hỏi mà các tool có cấu trúc ở trên không đáp ứng được.
    Chỉ SELECT (hoặc WITH ... SELECT), 1 statement duy nhất, tối đa 200 dòng
    (trường truncated cho biết kết quả có bị cắt không), chạy dưới 1 role
    DB chỉ có quyền SELECT. LUÔN schema-qualify tên bảng dạng
    `quotation.<table>` (vd `quotation.work_item`, không bao giờ dùng
    `work_item` trần hay `public.work_item`) -- không có schema `public`
    ở đây, tên bảng không qualify sẽ lỗi. Phía báo giá (quotation):
    project -> quotation -> package -> work_item -> work_step (work_item
    còn many-to-many với concept qua work_item_concept); quotation còn có
    các con scope_term/payment_term/warranty_term, và project có bảng
    anh em extra_quotation. Phía dự toán (cost estimation), theo từng
    project, tách biệt với báo giá: project -> estimation -> total_detail,
    và project -> estimation -> estimation_work_item (FK lỏng tới
    work_item.item_id, không phải dòng nào cũng map 1-1) -> labor_info
    (-> labor_info_process) và main_material; project -> sub_material
    (-> item_sub) và product_to_buy trực tiếp. Ưu tiên dùng các tool có
    cấu trúc ở trên thay vì escape hatch này bất cứ khi nào 1 tool đã trả
    lời được câu hỏi -- kết quả của chúng đã đúng và đầy đủ (trong giới
    hạn số dòng đã nêu nếu có), không cần xác minh lại ở đây."""
    try:
        validate_select_only(query)
    except ValueError as exc:
        return {"error": str(exc)}

    # Xin dư 1 dòng để biết kết quả có bị cắt hay không mà không phải đếm toàn bộ.
    limited_query = ensure_limit(query, RUN_SQL_MAX_ROWS + 1)

    try:
        with ReadonlySessionLocal() as session:
            result = session.execute(sql_text(limited_query))
            rows = [dict(row._mapping) for row in result.fetchmany(RUN_SQL_MAX_ROWS + 1)]
    except Exception as exc:
        # Best-effort boundary: a bad or overly expensive query from the agent
        # must surface as a tool error, not crash the MCP session.
        return {"error": str(exc)}

    truncated = len(rows) > RUN_SQL_MAX_ROWS
    rows = rows[:RUN_SQL_MAX_ROWS]
    return {"rows": rows, "row_count": len(rows), "truncated": truncated}


def main() -> None:
    mcp.run(
        transport="streamable-http",
        host=settings.mcp_server_host,
        port=settings.mcp_server_port,
        max_request_body_size=16 * 1024 * 1024,
    )


if __name__ == "__main__":
    main()
