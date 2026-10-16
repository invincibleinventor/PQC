// Self-checking harness: loads syndrome vectors produced by
// rtl/gen_and_check.py, runs the decoder and logs flips and status; the
// Python script compares the log with the golden model.
`timescale 1ns/1ps
module tb_lucid2d_dec;
    parameter MR = 4, MC = 5, MAXIT = 8, NT = 10;
    localparam R = 1 << MR, C = 1 << MC;
    reg clk = 0, rst = 1;
    always #2.5 clk = ~clk;   // 200 MHz
    reg ld_row_we = 0, ld_col_we = 0, start = 0;
    reg [MR-1:0] ld_row_addr; reg [MC:0] ld_row_data;
    reg [MC-1:0] ld_col_addr; reg [MR:0] ld_col_data;
    wire busy, done, converged, flip_valid;
    wire [3:0] scans; wire [MR-1:0] flip_row; wire [MC-1:0] flip_col;
    lucid2d_dec #(.MR(MR), .MC(MC), .MAXIT(MAXIT)) dut (
        .clk(clk), .rst(rst), .ld_row_we(ld_row_we), .ld_row_addr(ld_row_addr), .ld_row_data(ld_row_data),
        .ld_col_we(ld_col_we), .ld_col_addr(ld_col_addr), .ld_col_data(ld_col_data), .start(start),
        .busy(busy), .done(done), .converged(converged), .scans(scans),
        .flip_valid(flip_valid), .flip_row(flip_row), .flip_col(flip_col));
    reg [MC:0] rows [0:NT*R-1];
    reg [MR:0] cols [0:NT*C-1];
    integer t, i, f, cyc;
    initial begin
        $readmemh("vec_rows.hex", rows);
        $readmemh("vec_cols.hex", cols);
        f = $fopen("rtl_out.txt", "w");
        repeat (3) @(posedge clk);
        rst <= 0;
        for (t = 0; t < NT; t = t + 1) begin
            for (i = 0; i < R; i = i + 1) begin
                @(posedge clk); ld_row_we <= 1; ld_row_addr <= i; ld_row_data <= rows[t*R+i];
            end
            @(posedge clk); ld_row_we <= 0;
            for (i = 0; i < C; i = i + 1) begin
                @(posedge clk); ld_col_we <= 1; ld_col_addr <= i; ld_col_data <= cols[t*C+i];
            end
            @(posedge clk); ld_col_we <= 0; start <= 1;
            @(posedge clk); start <= 0; cyc = 0;
            $fwrite(f, "T %0d\n", t);
            while (!done) begin
                @(posedge clk); cyc = cyc + 1;
                if (flip_valid) $fwrite(f, "F %0d %0d\n", flip_row, flip_col);
            end
            $fwrite(f, "E %0d %0d %0d\n", converged, scans, cyc);
        end
        $fclose(f);
        $finish;
    end
endmodule
