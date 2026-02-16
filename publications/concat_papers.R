# Install if needed
# install.packages("RefManageR")

library(RefManageR)

# Path to folder containing .bib files
bib_folder <- "publications/bib_files"

# Get all .bib files in the folder
bib_files <- list.files(bib_folder, pattern = "\\.bib$", full.names = TRUE)

# Read all bib files
all_entries <- lapply(bib_files, ReadBib)

# Combine into one BibEntry object
combined_bib <- do.call(c, all_entries)

# Write combined bib file
WriteBib(combined_bib, file = "publications/papers.bib")