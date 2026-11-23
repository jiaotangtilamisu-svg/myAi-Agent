package com.simlect.api.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;
import java.util.List;

/** Strict read contract; never borrows the legacy missing-row-as-zero semantics. */
public class SkuStockBatchQueryDTO {
    @NotEmpty @Size(max = 200) @Valid
    private List<SkuStockQueryDTO> items;
    public List<SkuStockQueryDTO> getItems() { return items; }
    public void setItems(List<SkuStockQueryDTO> items) { this.items = items; }
}
