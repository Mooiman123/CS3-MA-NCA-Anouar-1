terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.50"
    }
  }
}

# Alle *.tf bestanden in deze map vormen samen de config.
# main.tf is bewust minimalistisch; de resources staan in de andere .tf bestanden.
