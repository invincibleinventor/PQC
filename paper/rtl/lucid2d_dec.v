// lucid2d_dec.v -- syndrome-domain iterative row/column SECDED decoder
//
// Holds the row-syndrome differences (R words of MC+1 bits) and column-
// syndrome differences (C words of MR+1 bits) of one R x C LUCID-2D tile.
// One row (row pass) or one column (column pass) is examined per cycle.
// A single-error syndrome produces a flip (row, col) on the output stream and
// XORs the SECDED column of the flipped position into the crossing column
// (row pass) or row (column pass) syndrome.  The key bits are never stored
// here; the flip stream is XOR-ed into the key buffer by the caller.
//
// Termination: the decoder stops after the first scan (row pass followed by
// column pass) that makes no correction, or after MAXIT+1 scans.  It is
// converged when the final scan made no correction and saw only zero
// syndromes.  Mirrors sim/syndrome_decoder_model.py cycle for cycle.

`timescale 1ns/1ps
module lucid2d_dec #(
    parameter MR    = 7,          // R = 2**MR rows
    parameter MC    = 7,          // C = 2**MC columns
    parameter MAXIT = 8,
    parameter IW    = (MR > MC) ? MR : MC
) (
    input  wire          clk,
    input  wire          rst,
    // syndrome load port (used while idle)
    input  wire          ld_row_we,
    input  wire [MR-1:0] ld_row_addr,
    input  wire [MC:0]   ld_row_data,
    input  wire          ld_col_we,
    input  wire [MC-1:0] ld_col_addr,
    input  wire [MR:0]   ld_col_data,
    input  wire          start,
    // status
    output reg           busy,
    output reg           done,
    output reg           converged,
    output reg  [3:0]    scans,
    // flip stream
    output reg           flip_valid,
    output reg  [MR-1:0] flip_row,
    output reg  [MC-1:0] flip_col
);
    localparam R = 1 << MR;
    localparam C = 1 << MC;

    reg [MC:0] drow [0:R-1];
    reg [MR:0] dcol [0:C-1];

    reg          phase;          // 0: row pass, 1: column pass
    reg [IW-1:0] idx;
    reg          flipped, nonzero;

    // current entry and decode
    wire [MC:0]   rd_row = drow[idx[MR-1:0]];
    wire [MR:0]   rd_col = dcol[idx[MC-1:0]];
    wire          r_single = rd_row[MC];
    wire          c_single = rd_col[MR];
    wire [MC-1:0] r_pos    = rd_row[MC-1:0];
    wire [MR-1:0] c_pos    = rd_col[MR-1:0];
    wire          cur_nz   = phase ? (rd_col != 0) : (rd_row != 0);
    wire          cur_fix  = phase ? c_single : r_single;
    wire          last_row = (idx[MR-1:0] == R-1);
    wire          last_col = (idx[MC-1:0] == C-1);
    wire          flipped_n = flipped | cur_fix;
    wire          nonzero_n = nonzero | cur_nz;

    integer k;
    always @(posedge clk) begin
        flip_valid <= 1'b0;
        done       <= 1'b0;
        if (rst) begin
            busy <= 1'b0; converged <= 1'b0; scans <= 4'd0;
            phase <= 1'b0; idx <= {IW{1'b0}}; flipped <= 1'b0; nonzero <= 1'b0;
        end else if (!busy) begin
            if (ld_row_we) drow[ld_row_addr] <= ld_row_data;
            if (ld_col_we) dcol[ld_col_addr] <= ld_col_data;
            if (start) begin
                busy <= 1'b1; converged <= 1'b0; scans <= 4'd0;
                phase <= 1'b0; idx <= {IW{1'b0}}; flipped <= 1'b0; nonzero <= 1'b0;
            end
        end else begin
            if (!phase) begin
                // ---------------- row pass ----------------
                if (r_single) begin
                    drow[idx[MR-1:0]] <= {(MC+1){1'b0}};
                    dcol[r_pos]       <= dcol[r_pos] ^ {1'b1, idx[MR-1:0]};
                    flip_valid <= 1'b1;
                    flip_row   <= idx[MR-1:0];
                    flip_col   <= r_pos;
                end
                flipped <= flipped_n;
                nonzero <= nonzero_n;
                if (last_row) begin
                    phase <= 1'b1;
                    idx   <= {IW{1'b0}};
                end else begin
                    idx <= idx + 1'b1;
                end
            end else begin
                // -------------- column pass ---------------
                if (c_single) begin
                    dcol[idx[MC-1:0]] <= {(MR+1){1'b0}};
                    drow[c_pos]       <= drow[c_pos] ^ {1'b1, idx[MC-1:0]};
                    flip_valid <= 1'b1;
                    flip_row   <= c_pos;
                    flip_col   <= idx[MC-1:0];
                end
                if (last_col) begin
                    // end of scan
                    scans   <= scans + 1'b1;
                    phase   <= 1'b0;
                    idx     <= {IW{1'b0}};
                    flipped <= 1'b0;
                    nonzero <= 1'b0;
                    if (!flipped_n) begin
                        busy <= 1'b0; done <= 1'b1; converged <= !nonzero_n;
                    end else if (scans == MAXIT) begin
                        busy <= 1'b0; done <= 1'b1; converged <= 1'b0;
                    end
                end else begin
                    idx     <= idx + 1'b1;
                    flipped <= flipped_n;
                    nonzero <= nonzero_n;
                end
            end
        end
    end
endmodule
